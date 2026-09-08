#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject configured-build symlinks that escape the current worktree."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def checked_links(repository: Path, trees: list[Path]) -> list[str]:
    root = repository.resolve()
    errors: list[str] = []
    for tree in trees:
        lexical_tree = repository / tree
        if not lexical_tree.is_dir():
            errors.append(f"missing build tree: {tree.as_posix()}")
            continue
        for directory, directories, files in os.walk(lexical_tree, followlinks=False):
            for name in sorted([*directories, *files]):
                link = Path(directory) / name
                if not link.is_symlink():
                    continue
                destination = link.resolve(strict=False)
                try:
                    destination.relative_to(root)
                except ValueError:
                    relative = link.relative_to(root).as_posix()
                    errors.append(f"build-tree symlink escapes repository: {relative}")
    return sorted(errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--tree", action="append", type=Path, required=True)
    arguments = parser.parse_args()
    errors = checked_links(arguments.repository, arguments.tree)
    if errors:
        for error in errors:
            print(f"build-tree-links: ERROR: {error}")
        return 1
    print("build-tree-links: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
