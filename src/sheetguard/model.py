from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WorkbookSnapshot:
    """Selected facts read directly from an XLSX package; never recalculated."""

    sheet_names: tuple[str, ...]
    formulas: dict[tuple[str, str], str]
    defined_names: dict[str, str]
    validations: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    sheet: Optional[str] = None
    cell: Optional[str] = None
    name: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None

    def as_dict(self) -> dict[str, Optional[str]]:
        return {
            "code": self.code,
            "message": self.message,
            "sheet": self.sheet,
            "cell": self.cell,
            "name": self.name,
            "expected": self.expected,
            "actual": self.actual,
        }
