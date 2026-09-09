#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Copy a verified source-closure manifest into an otherwise empty tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import re


def fail(message: str) -> None:
    raise SystemExit(f"materialize-source-closure: ERROR: {message}")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(131072), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_relative(value: str, label: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        fail(f"{label} is not a safe relative path")
    return Path(*path.parts)


def load_roots(declaration: Path, repository: Path) -> dict[str, tuple[Path, Path]]:
    document = json.loads(declaration.read_text(encoding="utf-8"))
    if document.get("schema") != 1 or not isinstance(document.get("roots"), list):
        fail("invalid roots declaration")
    result: dict[str, tuple[Path, Path]] = {}
    for item in document["roots"]:
        name = item.get("name")
        if not isinstance(name, str) or not name or name in result:
            fail("invalid or duplicate source root")
        relative = Path() if item.get("path") == "." else safe_relative(item.get("path", ""), "root path")
        source = (repository / relative).resolve()
        try:
            source.relative_to(repository)
        except ValueError:
            fail(f"source root escapes repository: {name}")
        result[name] = (source, relative)
    return result


def copy_checked(source: Path, destination: Path, expected: str) -> None:
    if not source.is_file() or digest(source) != expected:
        fail("source input is missing or changed")
    if destination.exists():
        if not destination.is_file() or digest(destination) != expected:
            fail("conflicting closure destination")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination, follow_symlinks=True)
    if digest(destination) != expected:
        fail("copied input failed hash verification")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    arguments = parser.parse_args()

    repository = arguments.repository.resolve()
    destination = arguments.destination.resolve()
    if destination == repository or repository in destination.parents:
        fail("destination must be outside the source repository")
    if destination.exists() and any(destination.iterdir()):
        fail("destination is not empty")
    roots = load_roots(arguments.roots, repository)
    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), list):
        fail("invalid source-closure manifest")

    copied: dict[Path, str] = {}
    copied_parents: set[Path] = set()
    copy_plan: dict[Path, tuple[Path, str]] = {}
    for item in manifest["files"]:
        if not isinstance(item, dict):
            fail("invalid manifest input")
        root_name = item.get("source_root")
        if root_name not in roots:
            fail("manifest names an undeclared source root")
        source_root, destination_root = roots[root_name]
        relative = safe_relative(item.get("path", ""), "manifest path")
        target = destination_root / relative
        expected = item.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            fail("manifest input lacks SHA-256")
        if target in copied or any(parent in copied for parent in target.parents) or target in copied_parents:
            fail("manifest inputs collide at destination")
        source = source_root / relative
        if not source.is_file() or source.is_symlink() or digest(source) != expected:
            fail(f"source input is missing or changed: {root_name}/{relative.as_posix()}")
        copied[target] = expected
        copied_parents.update(target.parents)
        copy_plan[target] = (source, expected)

    generated_items = manifest.get("generated_inputs", [])
    if not isinstance(generated_items, list):
        fail("generated inputs must be a list")
    for item in generated_items:
        if not isinstance(item, dict): fail("invalid generated input")
        relative = safe_relative(item.get("path", ""), "generated input path")
        expected = item.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            fail("generated input lacks SHA-256")
        if relative in copied or any(parent in copied for parent in relative.parents) or relative in copied_parents:
            fail("generated input collides at destination")
        source = repository / relative
        if not source.is_file() or source.is_symlink() or digest(source) != expected:
            fail(f"generated input is missing or changed: {relative.as_posix()}")
        copied[relative] = expected
        copied_parents.update(relative.parents)
        copy_plan[relative] = (source, expected)

    symlinked=set(); symlink_plan=[]; symlink_items=manifest.get("generated_symlinks", [])
    if not isinstance(symlink_items,list): fail("generated symlinks must be a list")
    for item in symlink_items:
        if not isinstance(item,dict): fail("invalid generated symlink")
        relative=safe_relative(item.get("path",""),"generated symlink path")
        target=safe_relative(item.get("target",""),"generated symlink target")
        if relative in copied or relative in symlinked: fail("generated symlink collides at destination")
        kind=item.get("target_type")
        if kind not in {"file","directory"}: fail("generated symlink target is missing or wrong type")
        symlink_plan.append((relative,target,kind)); symlinked.add(relative)
    for relative,target,kind in symlink_plan:
        if kind=="file" and target not in copy_plan: fail("generated symlink target is missing or wrong type")
        if kind=="directory" and not any(target in path.parents for path in copy_plan): fail("generated symlink target is missing or wrong type")
        if any(parent in symlinked for parent in relative.parents) or any(parent in symlinked for parent in (target,*target.parents)): fail("generated symlink topology traverses another symlink")
        if any(parent in copied for parent in relative.parents): fail("generated symlink collides at destination")
        if relative in copied_parents: fail("generated symlink collides at destination")

    # No destination mutation occurs until every row, byte hash, collision and
    # symlink target has passed preflight.
    destination.mkdir(parents=True, exist_ok=True)
    for relative,(source,expected) in copy_plan.items():
        copy_checked(source,destination/relative,expected)
    for relative,target,kind in symlink_plan:
        link=destination/relative; resolved=destination/target
        link.parent.mkdir(parents=True,exist_ok=True)
        link.symlink_to(Path(os.path.relpath(resolved,link.parent)))
        if not link.resolve().is_relative_to(destination) or link.resolve()!=resolved.resolve(): fail("materialized symlink escapes or differs")

    print(f"materialize-source-closure: copied {len(copied)} files and {len(symlinked)} symlinks")


if __name__ == "__main__":
    main()
