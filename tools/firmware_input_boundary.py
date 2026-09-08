#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify immutable archives, patches, and staged trees used by firmware builds."""

import argparse, hashlib, json
from pathlib import Path

SCHEMA = "brickwright/firmware-build-input-lock/v1"

def fail(message): raise SystemExit(f"firmware-input-boundary: ERROR: {message}")
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(131072), b""): h.update(block)
    return h.hexdigest()
def tree_sha(root):
    h = hashlib.sha256(); count = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and ".git" not in relative.parts:
            name = relative.as_posix().encode(); data = path.read_bytes()
            h.update(len(name).to_bytes(8, "big") + name)
            h.update(len(data).to_bytes(8, "big") + data); count += 1
    if not count: fail(f"staged tree is empty: {root}")
    return h.hexdigest()
def named(values):
    result = {}
    for value in values:
        if "=" not in value: fail(f"expected NAME=PATH: {value}")
        name, path = value.split("=", 1)
        if not name or name in result: fail(f"invalid or duplicate name: {name}")
        result[name] = Path(path)
    return result
def main():
    p=argparse.ArgumentParser(); p.add_argument("--lock",type=Path,default=Path("policy/firmware-build-inputs.lock.json")); p.add_argument("--repo",type=Path,default=Path(".")); p.add_argument("--stage",action="append",default=[]); p.add_argument("--archive",action="append",default=[]); a=p.parse_args()
    doc=json.loads(a.lock.read_text());
    if doc.get("schema") != SCHEMA: fail("invalid lock schema")
    stages, archives=named(a.stage), named(a.archive)
    known={x.get("name") for x in doc.get("sources",[])} | {x.get("name") for x in doc.get("host_tools",[])}
    if (set(stages)|set(archives))-known: fail("argument names an unknown component")
    for source in doc.get("sources",[]):
        name=source.get("name","")
        if not name or not source.get("license_expression") or not source.get("staged_tree_sha256"): fail(f"incomplete source declaration: {name}")
        for patch in source.get("patches",[]):
            path=(a.repo/patch["path"]).resolve()
            try: path.relative_to(a.repo.resolve())
            except ValueError: fail(f"patch escapes repository: {patch['path']}")
            if not path.is_file() or sha(path)!=patch["sha256"]: fail(f"patch hash mismatch: {patch['path']}")
        if name in stages:
            if tree_sha(stages[name]) != source["staged_tree_sha256"]: fail(f"staged tree hash mismatch: {name}")
        if name in archives:
            expected=source.get("archive_sha256")
            if not expected: fail(f"component has no single archive hash: {name}")
            if sha(archives[name]) != expected: fail(f"archive hash mismatch: {name}")
    for tool in doc.get("host_tools",[]):
        for key in ("name","repository","commit","archive_sha256","license_expression","outputs"):
            if not tool.get(key): fail(f"incomplete host-tool declaration: {tool.get('name','')}")
        if tool["name"] in archives and sha(archives[tool["name"]]) != tool["archive_sha256"]: fail(f"archive hash mismatch: {tool['name']}")
    print("firmware-input-boundary: verified")
if __name__ == "__main__": main()
