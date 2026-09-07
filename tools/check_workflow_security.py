#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Enforce immutable Actions and least-privilege workflow defaults."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
USE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if not re.search(r"(?m)^permissions:\s*\n(?:\s+\S.*\n)+", text):
        errors.append(f"{path.name}: missing explicit top-level permissions")
    if re.search(r"(?m)^\s+[a-z-]+:\s*write\s*(?:#.*)?$", text):
        errors.append(f"{path.name}: grants a write permission")
    if "timeout-minutes:" not in text:
        errors.append(f"{path.name}: jobs must have a timeout")
    for line_number, line in enumerate(text.splitlines(), 1):
        match = USE.match(line)
        if not match:
            continue
        action = match.group(1)
        if action.startswith("./"):
            continue
        if "@" not in action or not FULL_SHA.fullmatch(action.rsplit("@", 1)[1]):
            errors.append(f"{path.name}:{line_number}: action is not pinned to a full SHA")
    checkout_count = text.count("uses: actions/checkout@")
    if checkout_count != text.count("persist-credentials: false"):
        errors.append(f"{path.name}: every checkout must disable persisted credentials")
    return errors


def main() -> int:
    paths = sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")))
    errors = [error for path in paths for error in check(path)]
    if errors:
        print("\n".join(f"workflow-policy: ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"workflow-policy: checked {len(paths)} workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
