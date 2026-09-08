#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Produce exact evidence for toolchain files selected by a firmware link."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

SCHEMA = "brickwright/linked-runtime-evidence/v1"
DECLARATION_SCHEMA = "brickwright/runtime-input-declaration/v1"
MAP_INPUT = re.compile(r"(?<!\S)([^\s()]+\.a\(([^)]+\.o)\)|[^\s()]+\.(?:a|o))(?!\S)")


def fail(message: str) -> None:
    raise SystemExit(f"link-input-evidence: ERROR: {message}")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def relative_file(root: Path, raw: str) -> tuple[str, Path]:
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        fail(f"artifact path escapes toolchain: {raw}")
    lexical = root / relative.as_posix()
    resolved = lexical.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        fail(f"artifact symlink escapes toolchain: {raw}")
    if not resolved.is_file():
        fail(f"artifact is not a file: {raw}")
    return relative.as_posix(), resolved


def load_declarations(path: Path, root: Path, components: set[str]) -> dict[str, dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != DECLARATION_SCHEMA or not isinstance(document.get("artifacts"), list):
        fail("invalid runtime input declaration")
    result: dict[str, dict] = {}
    for raw in document["artifacts"]:
        name, actual = relative_file(root, raw.get("path", ""))
        component = raw.get("component")
        if component not in components:
            fail(f"artifact has unknown reviewed component: {name}")
        if name in result:
            fail(f"duplicate artifact declaration: {name}")
        result[name] = {"path": actual, "component": component}
    return result


def normalize_map_path(raw: str, map_path: Path, link_cwd: Path, root: Path) -> str | None:
    path = Path(raw)
    candidates = [path] if path.is_absolute() else [map_path.parent / path, link_cwd / path]
    matches = []
    for candidate in candidates:
        normalized = Path(os.path.abspath(candidate)).resolve()
        try:
            matches.append(normalized.relative_to(root).as_posix())
        except ValueError:
            continue
    matches = sorted(set(matches))
    if len(matches) > 1:
        fail(f"ambiguous relative map input: {raw}")
    return matches[0] if matches else None


def selected_inputs(maps: list[Path], link_cwd: Path, root: Path) -> tuple[dict[str, set[str]], list[dict]]:
    selected: dict[str, set[str]] = {}
    map_rows = []
    for map_path in maps:
        if not map_path.is_file():
            fail(f"link map is missing: {map_path}")
        map_rows.append({"path": map_path.name, "sha256": digest_file(map_path)})
        for match in MAP_INPUT.finditer(map_path.read_text(encoding="utf-8", errors="replace")):
            token, member = match.group(1), match.group(2)
            container = token[: token.index("(")] if member else token
            relative = normalize_map_path(container, map_path.resolve(), link_cwd, root)
            if relative is not None:
                selected.setdefault(relative, set())
                if member:
                    selected[relative].add(member)
    return selected, sorted(map_rows, key=lambda row: (row["path"], row["sha256"]))


def archive_members(ar: Path, archive: Path) -> list[str]:
    result = subprocess.run([ar, "t", archive], capture_output=True, text=True)
    if result.returncode:
        fail(f"cannot list archive {archive}: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line]


def member_bytes(ar: Path, archive: Path, member: str) -> bytes:
    result = subprocess.run([ar, "p", archive, member], capture_output=True)
    if result.returncode:
        fail(f"cannot extract {archive.name}({member})")
    return result.stdout


def produce(arguments: argparse.Namespace) -> dict:
    lock = json.loads(arguments.lock.read_text(encoding="utf-8"))
    components = set(lock.get("runtime_policy", {}))
    if not components:
        fail("toolchain lock has no runtime policy")
    root = arguments.toolchain_root.resolve()
    declarations = load_declarations(arguments.declarations, root, components)
    selected, maps = selected_inputs(arguments.map, arguments.link_cwd.resolve(), root)
    undeclared = sorted(set(selected) - set(declarations))
    stale = sorted(set(declarations) - set(selected))
    if undeclared or stale:
        fail(f"map and declarations differ; undeclared={undeclared}, stale={stale}")
    argv_document = json.loads(arguments.link_argv.read_text(encoding="utf-8"))
    if not isinstance(argv_document, list) or not argv_document or not all(isinstance(x, str) for x in argv_document):
        fail("link argv must be a nonempty JSON string array")
    ar = root / "bin" / "arm-none-eabi-ar"
    if not ar.is_file() or not os.access(ar, os.X_OK):
        fail("pinned arm-none-eabi-ar is missing")
    rows = []
    for name in sorted(selected):
        declaration = declarations[name]
        path = declaration["path"]
        members = []
        if selected[name]:
            available = archive_members(ar, path)
            for member in sorted(selected[name]):
                count = available.count(member)
                if count != 1:
                    fail(f"selected archive member is not unique: {name}({member}) count={count}")
                data = member_bytes(ar, path, member)
                members.append({"path": member, "sha256": digest_bytes(data)})
        rows.append({
            "path": name,
            "sha256": digest_file(path),
            "component": declaration["component"],
            "license_expression": lock["runtime_policy"][declaration["component"]]["license_expression"],
            "selected_members": members,
        })
    argv_bytes = (json.dumps(argv_document, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
    return {"schema": SCHEMA, "link_argv": argv_document, "link_argv_sha256": digest_bytes(argv_bytes),
            "maps": maps, "artifacts": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("policy/arm-toolchain.lock.json"))
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--declarations", type=Path, required=True)
    parser.add_argument("--link-argv", type=Path, required=True)
    parser.add_argument("--link-cwd", type=Path, required=True)
    parser.add_argument("--map", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    document = produce(arguments)
    arguments.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
