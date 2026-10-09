# SheetGuard 0.1.0

SheetGuard checks whether a saved `.xlsx` workbook still matches a small, explicit JSON contract. It reads OOXML package contents directly and does not recalculate formulas, edit workbooks, or launch Excel or LibreOffice.

## Try it

```powershell
python -m pip install -e ".[dev]"
sheetguard check examples/contract.json examples/budget-before.xlsx
sheetguard check examples/contract.json examples/budget-after.xlsx
```

The `budget-before.xlsx` example passes. The adversarial `budget-after.xlsx` exits with status 1 and reports the missing formula at `Summary!B2` and the changed validation at `Data!A2`.

## Scope and limits

Contracts in this release assert sheet names, exact formula text, workbook-scoped defined names, and data-validation type/anchor. Checks are limited to saved package contents: SheetGuard does not establish that formulas are correct, recalculate values, or repair files. Examples contain synthetic data only.

Release evidence: clean-install Python 3.13 environment and 10 tests passed; CI passed on Ubuntu and Windows with Python 3.10 and 3.13; independent review passed on commit `9e7538afb22a58d4ad1341fc5ddf4466d534611b`.
