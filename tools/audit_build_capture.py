#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit whether a build capture is sufficient for source-closure generation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re


TRACE_PREFIX = re.compile(r"^\s*(?:(?:\[pid\s+(\d+)\]|(\d+))\s+)?(.*)$")
CONNECT_RESULT = re.compile(r"^connect\(.*\)\s+=\s+(-?\d+)")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(131072), b""):
            value.update(chunk)
    return value.hexdigest()


def load_closure_tool() -> object:
    path = Path(__file__).with_name("source_closure.py")
    spec = importlib.util.spec_from_file_location("source_closure", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load source_closure.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_path(path: Path, tree: Path) -> str:
    """Return a stable identity without exposing the capture host layout."""
    try:
        relative = path.relative_to(tree)
    except ValueError:
        identity = hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest()[:16]
        return "$EXTERNAL/path-" + identity
    return "$TREE" if not relative.parts else "$TREE/" + relative.as_posix()


def successful_connects(trace: Path) -> tuple[int, int]:
    """Count connect attempts/results while joining strace resumed records."""
    attempts = 0
    successes = 0
    unfinished: dict[str, str] = {}
    for raw_line in trace.open("r", encoding="utf-8", errors="replace"):
        prefix = TRACE_PREFIX.match(raw_line.rstrip("\n"))
        if prefix is None:
            continue
        pid = prefix.group(1) or prefix.group(2) or "main"
        line = prefix.group(3)
        if line.startswith("connect(") and "<unfinished ...>" in line:
            unfinished[pid] = line.replace("<unfinished ...>", "")
            attempts += 1
            continue
        resumed = re.match(r"^<\.\.\.\s+connect\s+resumed>(.*)$", line)
        if resumed:
            line = unfinished.pop(pid, "connect(") + resumed.group(1)
        elif line.startswith("connect("):
            attempts += 1
        match = CONNECT_RESULT.match(line)
        if match and int(match.group(1)) >= 0:
            successes += 1
    return attempts, successes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--output")
    parser.add_argument(
        "--link-provenance-error",
        help="host-path-free reason a separate map/capture provenance check failed",
    )
    arguments = parser.parse_args()
    trace = Path(arguments.trace).resolve()
    cwd = Path(arguments.cwd).resolve()
    tree = Path(arguments.tree).resolve()
    closure = load_closure_tool()
    errors: list[str] = []
    non_file_entries: list[dict] = []
    unclassified_non_file: list[str] = []
    consumed_count = 0
    missing_count = 0
    non_file_count = 0
    external_count = 0
    connect_attempt_count, successful_connect_count = successful_connects(trace)
    if successful_connect_count:
        errors.append(
            "capture contains successful network connections: "
            f"count={successful_connect_count}"
        )
    try:
        consumed = closure.trace_paths(trace, cwd)
        consumed_count = len(consumed)
        missing_count = sum(not path.exists() for path in consumed)
        # A path that exists but is not a regular file cannot be hashed or
        # licensed, so it is neither a generated product nor a required input.
        # Directories are traversal metadata and character devices are kernel
        # interfaces; both are reported by name and kind. Any other kind stays
        # a blocker, because an unknown read must never be suppressed.
        for path in sorted(consumed):
            if not path.exists() or path.is_file():
                continue
            if path.is_dir():
                kind = "directory"
            elif path.is_char_device():
                kind = "character-device"
            elif path.is_block_device():
                kind = "block-device"
            elif path.is_fifo():
                kind = "fifo"
            elif path.is_socket():
                kind = "socket"
            else:
                kind = "unknown"
            non_file_entries.append({"path": public_path(path, tree), "kind": kind})
            if kind not in {"directory", "character-device"}:
                unclassified_non_file.append(public_path(path, tree))
        non_file_count = len(non_file_entries)
        external_count = sum(
            not path.is_relative_to(tree) for path in consumed if path.exists()
        )
        if missing_count or unclassified_non_file:
            errors.append(
                "trace includes generated, removed, or unclassifiable paths that "
                f"need classification: missing={missing_count}, "
                f"unclassified_non_file={len(unclassified_non_file)}"
            )
    except SystemExit as exception:
        errors.append(str(exception).removeprefix("source-closure: ERROR: "))
    depfiles = sorted(tree.rglob("*.d"))
    if len(depfiles) < 2:
        errors.append(
            "compiler dependency coverage is incomplete: "
            f"found {len(depfiles)} depfile(s)"
        )
    maps = sorted(tree.rglob("*.map"))
    if not maps:
        errors.append("link-map evidence is missing")
    report = {
        # Schema 4 separates trace readiness from independently checked final
        # link provenance. Schema 3's plain `ready` status was too broad.
        # counts. Schema 1 recorded counts alone, and
        # the same trace yields a different external count under a different
        # --cwd/--tree, so those numbers could not be reproduced or checked.
        "schema": 4,
        "scope": "trace-path-and-network-coverage-only",
        "capture": {
            "initial_cwd": public_path(cwd, tree),
            "tree": "$TREE",
        },
        "status": "trace-ready" if not errors else "incomplete",
        "link_provenance": {
            "status": "invalid" if arguments.link_provenance_error else "not-evaluated",
            **({"reason": arguments.link_provenance_error} if arguments.link_provenance_error else {}),
        },
        "trace": {"sha256": digest(trace), "lines": sum(1 for _ in trace.open("rb"))},
        "consumed_path_count": consumed_count,
        "missing_path_count": missing_count,
        "non_file_path_count": non_file_count,
        "non_file_paths": non_file_entries,
        "external_existing_path_count": external_count,
        "network_connect_attempt_count": connect_attempt_count,
        "successful_network_connect_count": successful_connect_count,
        "depfile_count": len(depfiles),
        "map_files": [path.relative_to(tree).as_posix() for path in maps],
        "errors": errors,
    }
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        Path(arguments.output).write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
