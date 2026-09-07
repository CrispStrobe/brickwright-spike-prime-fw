#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit whether a build capture is sufficient for source-closure generation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--output")
    arguments = parser.parse_args()
    trace = Path(arguments.trace).resolve()
    cwd = Path(arguments.cwd).resolve()
    tree = Path(arguments.tree).resolve()
    closure = load_closure_tool()
    errors: list[str] = []
    consumed_count = 0
    missing_count = 0
    non_file_count = 0
    external_count = 0
    try:
        consumed = closure.trace_paths(trace, cwd)
        consumed_count = len(consumed)
        missing_count = sum(not path.exists() for path in consumed)
        non_file_count = sum(path.exists() and not path.is_file() for path in consumed)
        external_count = sum(
            not path.is_relative_to(tree) for path in consumed if path.exists()
        )
        if missing_count or non_file_count:
            errors.append(
                "trace includes generated, removed, or non-file paths that need "
                f"classification: missing={missing_count}, non_file={non_file_count}"
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
        # Schema 2 records the invocation. Schema 1 recorded counts alone, and
        # the same trace yields a different external count under a different
        # --cwd/--tree, so those numbers could not be reproduced or checked.
        "schema": 2,
        "capture": {
            "initial_cwd": cwd.as_posix(),
            "tree": tree.as_posix(),
        },
        "status": "ready" if not errors else "incomplete",
        "trace": {"sha256": digest(trace), "lines": sum(1 for _ in trace.open("rb"))},
        "consumed_path_count": consumed_count,
        "missing_path_count": missing_count,
        "non_file_path_count": non_file_count,
        "external_existing_path_count": external_count,
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
