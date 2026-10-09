from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree
import sys

import pytest

# Keep acceptance tests runnable from a fresh source checkout without an
# editable install; published-package checks can still exercise the install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sheetguard.contract import check_contract
from sheetguard.ooxml import snapshot_workbook

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
CONTRACT_PATH = EXAMPLES / "contract.json"
BEFORE = EXAMPLES / "budget-before.xlsx"
AFTER = EXAMPLES / "budget-after.xlsx"


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    source = str(ROOT / "src")
    env["PYTHONPATH"] = source + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def test_example_before_satisfies_contract_and_exposes_package_facts() -> None:
    snapshot = snapshot_workbook(BEFORE)

    assert snapshot.sheet_names == ("Summary", "Data")
    assert snapshot.formulas[("Summary", "B2")] == "SUM(Data!B2:B3)"
    assert snapshot.formulas[("Data", "B4")] == "SUM(B2:B3)"
    assert snapshot.defined_names["Revenue"] == "'Summary'!$B$2"
    assert ("Data", "A2:A3", "list") in snapshot.validations
    assert check_contract(load_contract(), snapshot) == []


def test_example_after_reports_missing_formula_and_validation_anchor() -> None:
    findings = check_contract(load_contract(), snapshot_workbook(AFTER))

    codes = {finding.code for finding in findings}
    assert "formula.mismatch" in codes
    assert "validation.mismatch" in codes
    assert any(f.cell == "B2" and f.sheet == "Summary" for f in findings)
    assert any(f.cell == "A2" and f.sheet == "Data" for f in findings)


def test_contract_detects_sheet_formula_name_and_validation_mismatches() -> None:
    snapshot = snapshot_workbook(BEFORE)
    contract = {
        "version": 1,
        "sheets": ["Summary", "Missing"],
        "formulas": [{"sheet": "Summary", "cell": "B2", "formula": "AVERAGE(Data!B2:B3)"}],
        "defined_names": [{"name": "Revenue", "refers_to": "Data!$B$4"}],
        "validations": [{"sheet": "Data", "cell": "B2", "type": "whole"}],
    }

    findings = check_contract(contract, snapshot)
    codes = {finding.code for finding in findings}
    assert {"sheets.mismatch", "formula.mismatch", "defined_name.mismatch", "validation.mismatch"} <= codes


def test_workbook_sheet_relationships_select_the_related_parts(tmp_path: Path) -> None:
    """Sheet order/names are joined through workbook rel IDs, not guessed filenames."""
    reordered = tmp_path / "relationship-map.xlsx"
    with zipfile.ZipFile(BEFORE) as source, zipfile.ZipFile(reordered, "w") as target:
        for info in source.infolist():
            contents = source.read(info.filename)
            if info.filename == "xl/_rels/workbook.xml.rels":
                root = ElementTree.fromstring(contents)
                for relation in root:
                    if relation.attrib.get("Id") == "rId1":
                        relation.set("Target", "/xl/worksheets/sheet2.xml")
                    elif relation.attrib.get("Id") == "rId2":
                        relation.set("Target", "/xl/worksheets/sheet1.xml")
                contents = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(info, contents)

    snapshot = snapshot_workbook(reordered)
    assert snapshot.formulas[("Summary", "B4")] == "SUM(B2:B3)"
    assert snapshot.formulas[("Data", "B2")] == "SUM(Data!B2:B3)"


def test_defined_names_include_only_workbook_global_definitions(tmp_path: Path) -> None:
    scoped = tmp_path / "scoped-names.xlsx"
    with zipfile.ZipFile(BEFORE) as source, zipfile.ZipFile(scoped, "w") as target:
        for info in source.infolist():
            contents = source.read(info.filename)
            if info.filename == "xl/workbook.xml":
                root = ElementTree.fromstring(contents)
                namespace = root.tag.rsplit("}", 1)[0] + "}"
                defined_names = root.find(f"{namespace}definedNames")
                if defined_names is None:
                    defined_names = ElementTree.SubElement(root, f"{namespace}definedNames")
                # Same-name local definitions must not collide with or replace
                # the workbook-global definition. Local-only names stay local.
                ElementTree.SubElement(
                    defined_names, f"{namespace}definedName",
                    {"name": "Revenue", "localSheetId": "0"},
                ).text = "'Data'!$B$4"
                ElementTree.SubElement(
                    defined_names, f"{namespace}definedName",
                    {"name": "LocalOnly", "localSheetId": "1"},
                ).text = "'Data'!$A$2"
                contents = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(info, contents)

    snapshot = snapshot_workbook(scoped)
    assert snapshot.defined_names["Revenue"] == "'Summary'!$B$2"
    assert "LocalOnly" not in snapshot.defined_names
    findings = check_contract({
        "version": 1,
        "defined_names": [{"name": "LocalOnly", "refers_to": "'Data'!$A$2"}],
    }, snapshot)
    assert [finding.code for finding in findings] == ["defined_name.mismatch"]


def test_corrupt_and_missing_workbooks_fail_as_unreadable(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_bytes(b"not an OOXML zip package")

    for path in (corrupt, tmp_path / "absent.xlsx"):
        result = subprocess.run(
            [sys.executable, "-m", "sheetguard", "check", str(CONTRACT_PATH), str(path)],
            cwd=ROOT,
            env=cli_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2


def test_invalid_contract_and_invalid_cli_input_use_status_two(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"version": 99}', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "sheetguard", "check", str(malformed), str(BEFORE)],
        cwd=ROOT,
        env=cli_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2

    bad_args = subprocess.run(
        [sys.executable, "-m", "sheetguard", "unknown"],
        cwd=ROOT,
        env=cli_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert bad_args.returncode == 2


def test_cli_statuses_and_text_and_json_output_are_deterministic() -> None:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "sheetguard", "check", str(CONTRACT_PATH), *args],
            cwd=ROOT,
            env=cli_env(),
            text=True,
            capture_output=True,
            check=False,
        )

    text_pass_1 = run(str(BEFORE))
    text_pass_2 = run(str(BEFORE))
    assert text_pass_1.returncode == text_pass_2.returncode == 0
    assert text_pass_1.stdout == text_pass_2.stdout

    json_pass_1 = run(str(BEFORE), "--format", "json")
    json_pass_2 = run(str(BEFORE), "--format", "json")
    assert json_pass_1.returncode == json_pass_2.returncode == 0
    assert json_pass_1.stdout == json_pass_2.stdout
    assert json.loads(json_pass_1.stdout) == []

    mismatch = run(str(AFTER))
    assert mismatch.returncode == 1
    assert "Summary!B2" in mismatch.stdout

    json_mismatch = run(str(AFTER), "--format", "json")
    assert json_mismatch.returncode == 1
    assert json.loads(json_mismatch.stdout)
    assert json_mismatch.stdout == run(str(AFTER), "--format", "json").stdout


def test_workbooks_are_read_only_and_no_spreadsheet_engine_is_started(monkeypatch: pytest.MonkeyPatch) -> None:
    before_hashes = {p: digest(p) for p in (BEFORE, AFTER)}

    # The package reader and contract checker are pure reads. A child process
    # launch would be an unexpected dependency on Excel or LibreOffice.
    def forbidden_process(*args, **kwargs):
        raise AssertionError("SheetGuard must not launch a spreadsheet engine")

    monkeypatch.setattr(subprocess, "Popen", forbidden_process)
    for path in (BEFORE, AFTER):
        check_contract(load_contract(), snapshot_workbook(path))

    assert {p: digest(p) for p in (BEFORE, AFTER)} == before_hashes


def test_xlsx_examples_are_valid_zip_packages() -> None:
    for path in (BEFORE, AFTER):
        assert zipfile.is_zipfile(path)
