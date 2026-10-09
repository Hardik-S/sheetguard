"""Command line interface for read-only saved-workbook checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .contract import ContractError, check_contract
from .ooxml import snapshot_workbook


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sheetguard")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check a saved workbook against a JSON contract")
    check.add_argument("contract", type=Path)
    check.add_argument("workbook", type=Path)
    check.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        with args.contract.open("r", encoding="utf-8") as stream:
            contract = json.load(stream)
        findings = check_contract(contract, snapshot_workbook(args.workbook))
    except (OSError, UnicodeError, json.JSONDecodeError, ContractError, ValueError, KeyError) as exc:
        print(f"sheetguard: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Package readers can surface a variety of malformed-archive/XML
        # exceptions. They are invalid input, not an assertion mismatch.
        print(f"sheetguard: unable to read workbook: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps([finding.as_dict() for finding in findings], ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")))
    elif findings:
        for finding in findings:
            location = ""
            if finding.sheet is not None:
                location = finding.sheet + (f"!{finding.cell}" if finding.cell else "") + ": "
            elif finding.name is not None:
                location = f"{finding.name}: "
            print(f"{finding.code}: {location}{finding.message}")
    else:
        print("SheetGuard: all contract checks passed.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
