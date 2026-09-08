#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject compiler/linker products left in a configured capture tree."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess


BUILD_SUFFIXES = {".o", ".a", ".d", ".dep"}
BUILD_NAMES = {
    "nuttx", "nuttx.bin", "nuttx.hex", "nuttx.map", "System.map",
    "nuttx_user.elf", "nuttx_user.bin", "nuttx_user.hex",
    "nuttx_user.map", "User.map",
}


def residuals(repository: Path, trees: list[Path], allowed: set[Path]) -> list[str]:
    found: list[str] = []
    root = repository.resolve()
    pending: list[Path] = []
    for relative_tree in trees:
        tree = repository / relative_tree
        if not tree.is_dir():
            found.append(f"missing-tree:{relative_tree.as_posix()}")
            continue
        pending.append(tree)
    visited: set[Path] = set()
    while pending:
        directory = pending.pop()
        resolved_directory = directory.resolve()
        if resolved_directory in visited:
            continue
        try:
            resolved_directory.relative_to(root)
        except ValueError:
            found.append("escaping-directory-link")
            continue
        visited.add(resolved_directory)
        with os.scandir(resolved_directory) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=True):
                    pending.append(Path(entry.path))
                    continue
                name = entry.name
                if Path(name).suffix not in BUILD_SUFFIXES and name not in BUILD_NAMES:
                    continue
                path = Path(entry.path)
                relative = path.relative_to(root)
                if relative not in allowed:
                    found.append(relative.as_posix())
    return sorted(found)


def is_tracked(repository: Path, relative: Path) -> bool:
    absolute = repository / relative
    current = absolute.parent
    root = repository.resolve()
    while current == root or root in current.parents:
        if (current / ".git").exists():
            result = subprocess.run(
                ["git", "-C", current, "ls-files", "--error-unmatch", "--", absolute.relative_to(current)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        if current == root:
            break
        current = current.parent
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--tree", action="append", type=Path, required=True)
    parser.add_argument("--allow", action="append", type=Path, default=[])
    arguments = parser.parse_args()
    allowed = set()
    for path in arguments.allow:
        if path.is_absolute() or ".." in path.parts:
            print("capture-tree-clean: ERROR: allow path escapes repository")
            return 1
        if not is_tracked(arguments.repository.resolve(), path):
            print("capture-tree-clean: ERROR: allow path is not git-tracked")
            return 1
        allowed.add(path)
    found = residuals(arguments.repository, arguments.tree, allowed)
    if found:
        print(f"capture-tree-clean: ERROR: {len(found)} residual build products")
        for path in found[:20]:
            print(f"capture-tree-clean: residual: {path}")
        if len(found) > 20:
            print(f"capture-tree-clean: residual: ... and {len(found) - 20} more")
        return 1
    print("capture-tree-clean: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
