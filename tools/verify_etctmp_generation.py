#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed verification for the isolated board etctmp preprocessing proof."""
import argparse, hashlib, json, re, stat
from pathlib import Path, PurePosixPath

HEX = re.compile(r"[0-9a-f]{64}")
IMAGE = "sha256:8d304601acccf0fd2d6bcbf4e1ec1377b5e89cbdd669a60c1cf5c0e581b3c3fa"
INPUTS = {"boards/spike-prime-hub/src/etc/init.d/rcS", "boards/spike-prime-hub/src/etc/init.d/rc.sysinit", "nuttx/include/nuttx/config.h"}
OUTPUT_ROOT = "boards/spike-prime-hub/src/etctmp/etc/init.d"
OUTPUTS = {"rcS", "rc.sysinit"}
def command(source): return ["arm-none-eabi-gcc", "-E", "-P", "-x", "c", "-isystem", "$REPOSITORY/nuttx/include", "-isystem", "$REPOSITORY/nuttx/include/newlib", "-D__NuttX__", "-D__KERNEL__", "etc/init.d/"+source, "-o", "$OUTPUT/"+source]

def fail(message): raise SystemExit("etctmp-proof: ERROR: " + message)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def relative(value, label):
    if not isinstance(value, str): fail(label + " path is missing")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts: fail(label + " path is unsafe")
    return path
def regular(root, value, label):
    path = root.joinpath(*relative(value, label).parts)
    try:
        if not path.resolve().is_relative_to(root.resolve()): fail(label + " escapes root: " + value)
    except FileNotFoundError: fail(label + " is missing: " + value)
    try: mode = path.lstat().st_mode
    except FileNotFoundError: fail(label + " is missing: " + value)
    if not stat.S_ISREG(mode): fail(label + " is not a regular non-symlink file: " + value)
    return path
def hash_value(value, label):
    if not isinstance(value, str) or not HEX.fullmatch(value): fail(label + " has invalid SHA-256")
    return value

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof", required=True); parser.add_argument("--repository", required=True)
    args = parser.parse_args(); repo = Path(args.repository).resolve()
    proof = json.loads(Path(args.proof).read_text())
    if proof.get("schema") != "brickwright/etctmp-generation-proof/v1": fail("invalid schema")
    if proof.get("status") != "exact-output-match": fail("status is not exact-output-match")
    if proof.get("container_image") != IMAGE: fail("unexpected container image")
    if proof.get("isolation") != {"network_namespace": "none", "successful_connects": 0}: fail("invalid isolation claim")
    commands = proof.get("generator_commands")
    if commands != [command("rc.sysinit"), command("rcS")]: fail("generator commands differ from native contract")
    inputs = proof.get("generator_inputs")
    if not isinstance(inputs, list) or not inputs: fail("generator inputs are empty")
    seen = set()
    for item in inputs:
        label = item.get("path") if isinstance(item, dict) else None
        path = regular(repo, label, "generator input")
        if label in seen: fail("duplicate generator input: " + label)
        seen.add(label)
        if digest(path) != hash_value(item.get("sha256"), "generator input"): fail("generator input hash mismatch: " + label)
    if seen != INPUTS: fail("generator input set mismatch")
    root_label = proof.get("output_root")
    if root_label != OUTPUT_ROOT: fail("unexpected output root")
    output_root = repo.joinpath(*relative(root_label, "output root").parts)
    current = repo
    for component in relative(root_label, "output root").parts:
        current /= component
        if current.is_symlink(): fail("output root contains a symlink component")
    try:
        contained = output_root.resolve().is_relative_to(repo)
    except FileNotFoundError:
        contained = False
    if not contained or not output_root.is_dir(): fail("output root is not a contained real directory")
    outputs = proof.get("outputs")
    if not isinstance(outputs, list) or not outputs: fail("outputs are empty")
    expected = set()
    for item in outputs:
        label = item.get("path") if isinstance(item, dict) else None
        path = regular(output_root, label, "output")
        if label in expected: fail("duplicate output: " + label)
        expected.add(label)
        if digest(path) != hash_value(item.get("sha256"), "output"): fail("output hash mismatch: " + label)
    if expected != OUTPUTS: fail("declared output set mismatch")
    actual = set()
    for path in output_root.rglob("*"):
        if path.is_symlink() or not path.is_file(): fail("non-regular output artifact")
        actual.add(path.relative_to(output_root).as_posix())
    if actual != expected: fail("output set mismatch")
    print(f"etctmp-proof: verified {len(outputs)} outputs")
if __name__ == "__main__": main()
