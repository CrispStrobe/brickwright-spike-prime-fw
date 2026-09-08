#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Transparent ARM tool wrapper preserving compile dependencies and link argv."""

from __future__ import annotations
import hashlib, json, os, shlex, subprocess, sys
from pathlib import Path

TOOLS = {"arm-none-eabi-gcc", "arm-none-eabi-g++", "arm-none-eabi-ld"}

def die(message: str) -> None:
    raise SystemExit(f"capture-arm-invocation: ERROR: {message}")

def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)

def output_of(argv: list[str]) -> str | None:
    for index, value in enumerate(argv[:-1]):
        if value == "-o": return argv[index + 1]
    for value in argv:
        if value.startswith("-o") and len(value) > 2: return value[2:]
    return None

def identity(tool: str, cwd: Path, argv: list[str]) -> str:
    value = json.dumps([tool, cwd.as_posix(), argv], separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()

def run_wrapper() -> int:
    tool = Path(sys.argv[0]).name
    if tool not in TOOLS: die(f"unsupported wrapper name: {tool}")
    real_value = os.environ.get("BRICKWRIGHT_REAL_ARM_BIN")
    capture_value = os.environ.get("BRICKWRIGHT_CAPTURE_DIR")
    if not real_value or not capture_value: die("capture environment is incomplete")
    real_bin = Path(real_value); capture = Path(capture_value)
    if not real_bin.is_dir(): die("capture environment is incomplete")
    cwd = Path.cwd().resolve(); original = sys.argv[1:]; invoked = list(original)
    output = output_of(original); compiling = "-c" in original and output is not None
    key = identity(tool, cwd, original)
    depfile = None
    if compiling and not any(x in original for x in ("-M", "-MM", "-MD", "-MMD", "-MF")):
        depfile = capture / "depfiles" / f"{key}.d"
        depfile.parent.mkdir(parents=True, exist_ok=True)
        invoked += ["-MD", "-MF", str(depfile)]
    responses = []
    for value in original:
        if value.startswith("@"):
            source = (cwd / value[1:]).resolve()
            if not source.is_file(): die(f"response file is missing: {value}")
            data = source.read_bytes(); digest = hashlib.sha256(data).hexdigest()
            destination = capture / "responses" / f"{digest}.rsp"
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists(): destination.write_bytes(data)
            responses.append({"argument": value, "sha256": digest, "path": f"responses/{digest}.rsp"})
    result = subprocess.run([real_bin / tool, *invoked])
    if result.returncode == 0:
        kind = "compile" if compiling else "link"
        atomic_json(capture / f"{kind}s" / f"{key}.json", {
            "schema": "brickwright/tool-invocation/v1", "tool": tool,
            "cwd": cwd.as_posix(), "argv": original, "output": output,
            "depfile": str(depfile) if depfile else None, "response_files": responses,
        })
    return result.returncode

def prepare(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve()
    for tool in sorted(TOOLS):
        destination = directory / tool
        if destination.exists() or destination.is_symlink(): destination.unlink()
        destination.symlink_to(source)

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "prepare": prepare(Path(sys.argv[2]))
    else: raise SystemExit(run_wrapper())
