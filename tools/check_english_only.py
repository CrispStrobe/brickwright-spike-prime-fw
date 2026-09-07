#!/usr/bin/env python3
"""Reject CJK text in project-owned tracked source files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


CJK_RE = re.compile(
    "["
    "\u3040-\u30ff"  # Hiragana and Katakana
    "\u3400-\u4dbf"  # CJK Extension A
    "\u4e00-\u9fff"  # CJK Unified Ideographs
    "\uac00-\ud7af"  # Hangul syllables
    "]"
)

# Imported upstream material is not project-owned. Keep this exception narrow;
# findings are still reported so reviewers can distinguish them from binaries.
THIRD_PARTY_PREFIXES = ("third_party/",)


def is_third_party(path: str) -> bool:
    return path.startswith(THIRD_PARTY_PREFIXES)


def cjk_lines(text: str) -> list[tuple[int, str]]:
    """Return one-based line numbers and text for lines containing CJK."""
    return [
        (number, line)
        for number, line in enumerate(text.splitlines(), 1)
        if CJK_RE.search(line)
    ]


def tracked_paths(root: Path) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root, stderr=subprocess.DEVNULL
    )
    return [path for path in output.decode("utf-8").split("\0") if path]


def scan(root: Path) -> tuple[list[tuple[str, int, str]], list[tuple[str, int, str]]]:
    violations: list[tuple[str, int, str]] = []
    third_party_findings: list[tuple[str, int, str]] = []

    for relative in tracked_paths(root):
        path = root / relative
        if not path.is_file():  # Includes uninitialized submodule gitlinks.
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # Binary and non-UTF-8 payloads are out of scope.
            continue

        target = third_party_findings if is_third_party(relative) else violations
        target.extend((relative, line, content) for line, content in cjk_lines(text))

    return violations, third_party_findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations, third_party_findings = scan(root)

    for path, line, content in third_party_findings:
        print(f"third-party CJK (informational): {path}:{line}: {content}")
    for path, line, content in violations:
        print(f"project-owned CJK: {path}:{line}: {content}", file=sys.stderr)

    if violations:
        print(
            f"English-only source policy failed with {len(violations)} finding(s).",
            file=sys.stderr,
        )
        return 1

    print("English-only source policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
