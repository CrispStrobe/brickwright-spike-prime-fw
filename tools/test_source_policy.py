#!/usr/bin/env python3
"""Black-box regression test for source-policy rejection."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ROOT / "apps" / "btsensor" / "chipset" / "cc256x_init_script.c"
FORBIDDEN_ARCHIVE = ROOT / "source-policy-fixture.bin.gz"
FORBIDDEN_REFERENCE = ROOT / "source-policy-reference.txt"


def run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def main() -> None:
    if FORBIDDEN.exists():
        raise SystemExit(f"test precondition failed: {FORBIDDEN} already exists")

    baseline = run("git", "write-tree", env=os.environ.copy())
    if baseline.returncode:
        raise SystemExit(baseline.stderr)
    baseline_tree = baseline.stdout.strip()

    with tempfile.TemporaryDirectory(prefix="source-policy-test-") as temp_dir:
        index = Path(temp_dir) / "index"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index)
        read_tree = run("git", "read-tree", baseline_tree, env=env)
        if read_tree.returncode:
            raise SystemExit(read_tree.stderr)

        try:
            FORBIDDEN.parent.mkdir(parents=True, exist_ok=True)
            FORBIDDEN.write_text("test fixture, not TI material\n", encoding="utf-8")
            add = run("git", "add", str(FORBIDDEN.relative_to(ROOT)), env=env)
            if add.returncode:
                raise SystemExit(add.stderr)
            check = run("python3", "tools/check_source_policy.py", env=env)
            if check.returncode == 0:
                raise SystemExit("source policy accepted a forbidden tracked path")
            expected = "forbidden tracked paths"
            if expected not in check.stderr:
                raise SystemExit(
                    f"source policy failed for the wrong reason:\n{check.stderr}"
                )
        finally:
            FORBIDDEN.unlink(missing_ok=True)
            FORBIDDEN.parent.rmdir()

    with tempfile.TemporaryDirectory(prefix="source-policy-archive-test-") as temp_dir:
        index = Path(temp_dir) / "index"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index)
        read_tree = run("git", "read-tree", baseline_tree, env=env)
        if read_tree.returncode:
            raise SystemExit(read_tree.stderr)

        try:
            FORBIDDEN_ARCHIVE.write_bytes(b"not an actual firmware archive\n")
            add = run("git", "add", str(FORBIDDEN_ARCHIVE.relative_to(ROOT)), env=env)
            if add.returncode:
                raise SystemExit(add.stderr)
            check = run("python3", "tools/check_source_policy.py", env=env)
            if check.returncode == 0:
                raise SystemExit("source policy accepted a compressed binary path")
            if "tracked build artifacts" not in check.stderr:
                raise SystemExit(
                    f"archive policy failed for the wrong reason:\n{check.stderr}"
                )
        finally:
            FORBIDDEN_ARCHIVE.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="source-policy-reference-test-") as temp_dir:
        index = Path(temp_dir) / "index"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index)
        read_tree = run("git", "read-tree", baseline_tree, env=env)
        if read_tree.returncode:
            raise SystemExit(read_tree.stderr)
        try:
            FORBIDDEN_REFERENCE.write_text(
                "private source: " + "spike-firmware" + "-backups\n",
                encoding="utf-8",
            )
            add = run("git", "add", str(FORBIDDEN_REFERENCE.relative_to(ROOT)), env=env)
            if add.returncode:
                raise SystemExit(add.stderr)
            check = run("python3", "tools/check_source_policy.py", env=env)
            if check.returncode == 0:
                raise SystemExit("source policy accepted a private-repository reference")
            if "forbidden public repository references" not in check.stderr:
                raise SystemExit(
                    f"reference policy failed for the wrong reason:\n{check.stderr}"
                )
        finally:
            FORBIDDEN_REFERENCE.unlink(missing_ok=True)

    print("source-policy-test: path, archive, and private reference rejected")


if __name__ == "__main__":
    main()
