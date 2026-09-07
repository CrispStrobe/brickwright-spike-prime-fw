#!/usr/bin/env python3
"""Reject history and obsolete Bluetooth claims in live project documents."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_FILES = (
    "README.md",
    "PLAN.md",
    "CLAUDE.md",
    "SAFETY.md",
    "THIRD_PARTY.md",
    "docs/en/drivers/implementation-plan.md",
    "docs/en/drivers/bluetooth.md",
    "docs/en/project/provenance.md",
    "docs/en/nuttx/upstream-issues.md",
)

FORBIDDEN = (
    (re.compile(r"(?im)^\s*[-*]\s*\[(?:x|~|!)\]"), "completed/in-progress marker"),
    (re.compile(r"(?im)^#+\s*(?:checkpoint log|status legend)\s*$"), "checkpoint log"),
    (re.compile(r"(?i)CC2564C.{0,30}\bv1\.4\b|\bv1\.4\b.{0,30}CC2564C"), "obsolete CC2564C v1.4 claim"),
    (re.compile(r"(?i)pybricks-baselined.{0,60}service pack"), "obsolete payload provenance"),
    (re.compile(r"(?i)(?:patch|patched|patching).{0,50}eHCILL|eHCILL.{0,50}(?:patch|patched|patching)"), "modified eHCILL payload claim"),
    (re.compile(r"(?i)^#+\s*why\s+btstack\s*$", re.MULTILINE), "obsolete BTstack design"),
)


def check(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in LIVE_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: missing live document")
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, label in FORBIDDEN:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{relative}:{line}: {label}")
    return errors


def main() -> int:
    errors = check()
    if errors:
        print("Live-document policy violations:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Live-document policy passed ({len(LIVE_FILES)} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
