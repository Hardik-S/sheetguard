# SheetGuard 0.1 independent release review

**Reviewed commit:** `9e7538afb22a58d4ad1341fc5ddf4466d534611b`
**Scope:** Issue #4 release gate; implementation and tests reviewed at the exact commit above.
**Recommendation: PASS.** The prior P2 defined-name scope defect is fixed and covered by a regression test. No remaining material release finding was identified in this scoped review.

## Follow-up: defined-name scope fix

The change in `src/sheetguard/ooxml.py:133-137` now skips `<definedName>` elements that have `localSheetId`, keeping worksheet-local definitions out of the workbook-global snapshot. This preserves a same-spelling global definition and avoids allowing a local-only definition to satisfy a global contract assertion.

The new regression test, `tests/test_acceptance.py:101-131`, constructs both cases in one XLSX fixture: a local `Revenue` alongside the global `Revenue`, plus local-only `LocalOnly`. It asserts the global `Revenue` value survives, `LocalOnly` is absent from the global snapshot, and a contract requiring that local-only name reports `defined_name.mismatch`. This directly covers both reported reproductions.

**Resolution:** The previous P2 finding is closed. The new test passed on the reviewed commit.

## Other review coverage

- **Raw OOXML relationship/path handling:** Workbook relationship IDs are joined to their declared targets. Duplicate IDs, external worksheet relationships, missing parts, backslashes, and normalized `..` escapes are rejected. Targets are read from the ZIP in read mode and package members are not extracted. Absolute package targets normalize to package-relative names. No traversal defect was found in the reviewed logic.
- **Read-only / no calculation:** The implementation reads XML bytes from `ZipFile(..., "r")`; it does not launch Excel/LibreOffice, calculate cached values, or execute formulas/macros. The existing read-only test checks example hashes and forbids `subprocess.Popen`. No spreadsheet engine was launched during this review.
- **Formula and validation extraction:** Formula text is read from worksheet `<f>` elements. Validation anchors use the first cell of each `sqref` area, and covered non-anchor cells do not count. The before/after examples demonstrate formula and validation mismatch reporting.
- **Contract and CLI:** Contract shape validation rejects unknown keys, invalid version types, malformed arrays/objects, missing fields, and empty assertion strings. Findings report the asserted sheet/cell or name. JSON is compact and key-sorted. Observed status codes are `0` for passing assertions and `1` for mismatches; malformed-input and argparse status `2` behavior remains covered by the existing suite.
- **Non-blocking test coverage note:** Relationship escape and external-target rejection are code-reviewed but still lack dedicated adversarial fixtures. No defect was reproduced in those paths. This is not a release blocker for this commit.
- **Clean-install quickstart:** Not run because the documented venv creation and editable install would modify repository paths outside the sole owned artifact. The pre-existing installed CLI was exercised against both example workbooks.

## Exact commands and results

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py::test_defined_names_include_only_workbook_global_definitions
```

Result: `1 passed in 0.05s`.

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result: `10 passed in 3.63s`.

```powershell
.\.venv\Scripts\sheetguard.exe check examples\contract.json examples\budget-before.xlsx
```

Result: printed `SheetGuard: all contract checks passed.`; exit `0`.

```powershell
.\.venv\Scripts\sheetguard.exe check examples\contract.json examples\budget-after.xlsx
```

Result: reported `formula.mismatch` at `Summary!B2` and `validation.mismatch` at `Data!A2`; exit `1`.

The checkout was at the reviewed SHA before validation. Only `reviews/release-review.md` was modified for this review receipt; no implementation or test files were changed.
