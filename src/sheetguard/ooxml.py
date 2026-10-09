"""Read selected workbook facts directly from an XLSX OOXML package.

This module deliberately treats a workbook as an inert ZIP of XML parts. It
does not use a spreadsheet engine, extract package members, or modify input.
"""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

from sheetguard.model import WorkbookSnapshot


_WORKBOOK_PART = "xl/workbook.xml"
_WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"


def _local_name(tag: str) -> str:
    """Return an XML element/attribute local name without relying on prefixes."""
    return tag.rsplit("}", 1)[-1]


def _children(element: ElementTree.Element, name: str) -> Iterable[ElementTree.Element]:
    return (child for child in element if _local_name(child.tag) == name)


def _required_part(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise ValueError(f"XLSX package is missing required part '{name}'") from exc
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Could not read XLSX package part '{name}': {exc}") from exc


def _parse_xml(data: bytes, part: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"XLSX package part '{part}' contains invalid XML: {exc}") from exc


def _relationship_target(target: str, source_part: str) -> str:
    """Resolve an OPC relationship target to a safe package member name."""
    if not target or "\\" in target:
        raise ValueError(f"Invalid worksheet relationship target: {target!r}")
    if target.startswith("/"):
        resolved = posixpath.normpath(target.lstrip("/"))
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))
    if resolved in ("", ".") or resolved == ".." or resolved.startswith("../"):
        raise ValueError(f"Worksheet relationship escapes the XLSX package: {target!r}")
    return resolved


def snapshot_workbook(path: str | Path) -> WorkbookSnapshot:
    """Read sheet names, formulas, defined names, and validation anchors.

    Raises ``ValueError`` with the problematic package part or relationship
    when the input is not a usable XLSX package.
    """
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Could not open XLSX package '{path}': {exc}") from exc

    with archive:
        names = set(archive.namelist())
        if _WORKBOOK_PART not in names:
            raise ValueError(f"XLSX package is missing required part '{_WORKBOOK_PART}'")
        if _WORKBOOK_RELS_PART not in names:
            raise ValueError(f"XLSX package is missing required part '{_WORKBOOK_RELS_PART}'")

        workbook = _parse_xml(_required_part(archive, _WORKBOOK_PART), _WORKBOOK_PART)
        relationships = _parse_xml(
            _required_part(archive, _WORKBOOK_RELS_PART), _WORKBOOK_RELS_PART
        )

        rel_by_id: dict[str, tuple[str, str | None, str]] = {}
        for relationship in _children(relationships, "Relationship"):
            rel_id = relationship.get("Id")
            rel_type = relationship.get("Type", "")
            target = relationship.get("Target")
            if rel_id:
                if rel_id in rel_by_id:
                    raise ValueError(f"Duplicate workbook relationship ID {rel_id!r}")
                rel_by_id[rel_id] = (
                    target or "", relationship.get("TargetMode"), rel_type
                )

        sheet_names: list[str] = []
        sheet_parts: list[tuple[str, str]] = []
        for sheet in _children(workbook, "sheets"):
            for entry in _children(sheet, "sheet"):
                sheet_name = entry.get("name")
                rel_id = next(
                    (value for key, value in entry.attrib.items() if _local_name(key) == "id"),
                    None,
                )
                if not sheet_name or not rel_id:
                    raise ValueError("Workbook contains a sheet without a name or relationship ID")
                if sheet_name in sheet_names:
                    raise ValueError(f"Workbook contains duplicate sheet name {sheet_name!r}")
                if rel_id not in rel_by_id:
                    raise ValueError(
                        f"Worksheet '{sheet_name}' references missing relationship {rel_id!r}"
                    )
                target, target_mode, rel_type = rel_by_id[rel_id]
                if target_mode and target_mode.lower() == "external":
                    raise ValueError(f"Worksheet '{sheet_name}' has an external relationship")
                if not rel_type.rstrip("/").endswith("/worksheet"):
                    raise ValueError(
                        f"Worksheet '{sheet_name}' references a non-worksheet relationship"
                    )
                part = _relationship_target(target, _WORKBOOK_PART)
                if part not in names:
                    raise ValueError(
                        f"Worksheet '{sheet_name}' relationship points to missing part '{part}'"
                    )
                sheet_names.append(sheet_name)
                sheet_parts.append((sheet_name, part))

        if not sheet_names:
            raise ValueError("Workbook contains no worksheets")

        defined_names: dict[str, str] = {}
        for container in _children(workbook, "definedNames"):
            for defined_name in _children(container, "definedName"):
                name = defined_name.get("name")
                if not name:
                    raise ValueError("Workbook contains a defined name without a name")
                if name in defined_names:
                    raise ValueError(f"Workbook contains duplicate defined name {name!r}")
                defined_names[name] = defined_name.text or ""

        formulas: dict[tuple[str, str], str] = {}
        validations: list[tuple[str, str, str]] = []
        for sheet_name, part in sheet_parts:
            worksheet = _parse_xml(_required_part(archive, part), part)
            for cell in worksheet.iter():
                if _local_name(cell.tag) != "c":
                    continue
                address = cell.get("r")
                if not address:
                    raise ValueError(f"Worksheet '{sheet_name}' contains a cell without an address")
                for formula in _children(cell, "f"):
                    formulas[(sheet_name, address)] = formula.text or ""
            for container in _children(worksheet, "dataValidations"):
                for validation in _children(container, "dataValidation"):
                    validations.append(
                        (sheet_name, validation.get("sqref", ""), validation.get("type", ""))
                    )

        return WorkbookSnapshot(
            sheet_names=tuple(sheet_names),
            formulas=formulas,
            defined_names=defined_names,
            validations=tuple(validations),
        )
