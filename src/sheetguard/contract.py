"""Validation for SheetGuard's version 1 JSON contract."""

from __future__ import annotations

import re

from .model import Finding, WorkbookSnapshot


class ContractError(ValueError):
    """Raised when a contract does not conform to the supported schema."""


def validate_contract_shape(contract: object) -> dict[str, object]:
    """Validate and return a normalized v1 contract, raising ``ContractError``."""
    if not isinstance(contract, dict):
        raise ContractError("contract must be a JSON object")
    if type(contract.get("version")) is not int or contract["version"] != 1:
        raise ContractError("version must be the integer 1")
    allowed = {"version", "sheets", "formulas", "defined_names", "validations"}
    unknown = sorted(set(contract) - allowed)
    if unknown:
        raise ContractError(f"unknown contract key(s): {', '.join(map(str, unknown))}")

    normalized: dict[str, object] = {"version": 1}
    if "sheets" in contract:
        sheets = contract["sheets"]
        if not isinstance(sheets, list) or any(not isinstance(item, str) or not item for item in sheets):
            raise ContractError("sheets must be an array of non-empty strings")
        if len(set(sheets)) != len(sheets):
            raise ContractError("sheets must not contain duplicates")
        normalized["sheets"] = sheets

    specifications = {
        "formulas": ("sheet", "cell", "formula"),
        "defined_names": ("name", "refers_to"),
        "validations": ("sheet", "cell", "type"),
    }
    for key, fields in specifications.items():
        items = contract.get(key, [])
        if not isinstance(items, list):
            raise ContractError(f"{key} must be an array")
        for index, item in enumerate(items):
            if not isinstance(item, dict) or set(item) != set(fields):
                raise ContractError(f"{key}[{index}] must contain exactly: {', '.join(fields)}")
            for field in fields:
                if not isinstance(item[field], str) or not item[field]:
                    raise ContractError(f"{key}[{index}].{field} must be a non-empty string")
        normalized[key] = items
    return normalized


def check_contract(contract: object, snapshot: WorkbookSnapshot) -> list[Finding]:
    """Compare declared v1 assertions with facts parsed from a saved workbook."""
    spec = validate_contract_shape(contract)
    findings: list[Finding] = []

    expected_sheets = spec.get("sheets")
    if expected_sheets is not None and tuple(expected_sheets) != snapshot.sheet_names:
        findings.append(Finding(
            "sheets.mismatch", "Workbook sheet names do not match the contract.",
            expected=", ".join(expected_sheets), actual=", ".join(snapshot.sheet_names),
        ))

    for item in spec["formulas"]:
        key = (item["sheet"], item["cell"])
        actual = snapshot.formulas.get(key)
        if actual != item["formula"]:
            findings.append(Finding(
                "formula.mismatch", "Formula does not match the contract.",
                sheet=item["sheet"], cell=item["cell"], expected=item["formula"], actual=actual,
            ))

    for item in spec["defined_names"]:
        actual = snapshot.defined_names.get(item["name"])
        if actual != item["refers_to"]:
            findings.append(Finding(
                "defined_name.mismatch", "Defined name reference does not match the contract.",
                name=item["name"], expected=item["refers_to"], actual=actual,
            ))

    def has_anchor(sqref: str, cell: str) -> bool:
        # OOXML sqref may contain one or more ranges. Only each range's
        # upper-left cell is a validation anchor; covered cells do not count.
        for area in sqref.split():
            first = area.split(":", 1)[0].replace("$", "")
            if first.upper() == cell.replace("$", "").upper():
                return True
            # Keep malformed or unusual sqref text from being interpreted as
            # a cell reference accidentally.
            if not re.fullmatch(r"[A-Za-z]{1,3}[1-9][0-9]*", first):
                continue
        return False

    for item in spec["validations"]:
        matches = [kind for sheet, sqref, kind in snapshot.validations
                   if sheet == item["sheet"] and has_anchor(sqref, item["cell"])]
        if item["type"] not in matches:
            matching_anchor = next(
                iter(matches),
                None,
            )
            findings.append(Finding(
                "validation.mismatch", "Validation anchor or type does not match the contract.",
                sheet=item["sheet"], cell=item["cell"], expected=item["type"], actual=matching_anchor,
            ))
    return findings
