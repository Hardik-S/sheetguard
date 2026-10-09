# SheetGuard

SheetGuard checks a saved `.xlsx` file against a small JSON contract. It reads the workbook package without changing it or asking Excel/LibreOffice to recalculate formulas.

## Quickstart

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
sheetguard check examples\contract.json examples\budget-after.xlsx
```

The `budget-after.xlsx` example intentionally loses a declared formula and list validation, so the command exits `1` with the affected sheet and cell. The corresponding intact workbook is `examples/budget-before.xlsx`.

## Contract

A version 1 JSON contract may assert exact sheet names, formula text at selected cells, defined-name references, and validation anchors:

```json
{
  "version": 1,
  "sheets": ["Summary", "Data"],
  "formulas": [
    {"sheet": "Summary", "cell": "B2", "formula": "SUM(Data!B2:B3)"}
  ],
  "defined_names": [
    {"name": "Revenue", "refers_to": "Summary!$B$2"}
  ],
  "validations": [
    {"sheet": "Data", "cell": "A2", "type": "list"}
  ]
}
```

Output is deterministic. `--format json` emits machine-readable findings. Exit codes are `0` for passing assertions, `1` for workbook mismatches, and `2` for invalid input or an unreadable package.

## Boundaries

SheetGuard checks declared facts in the saved OOXML package. It does not verify whether a formula is mathematically correct, calculate cached values, preserve workbook features by editing files, render spreadsheets, or replace broader workbook auditing tools. It never launches a spreadsheet engine.
