# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/toolchain_boundary.py"


class ToolchainBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "arm"
        (self.root / "bin").mkdir(parents=True)
        compiler = self.root / "bin/arm-none-eabi-gcc"
        compiler.write_text("#!/bin/sh\necho 13.2.1\n")
        compiler.chmod(0o755)
        for name in ("ar", "ld", "nm", "objcopy", "size"):
            target = self.root / "bin" / f"arm-none-eabi-{name}"
            target.write_text("#!/bin/sh\nexit 0\n")
            target.chmod(0o755)
        (self.root / "lib").mkdir()
        self.runtime = self.root / "lib/libgcc.a"
        self.runtime.write_bytes(b"synthetic runtime")
        self.lock = self.base / "lock.json"
        self.lock.write_text(json.dumps({
            "schema": "brickwright/arm-toolchain-lock/v1",
            "archive": {"url": "https://example.invalid/toolchain", "sha256": "a" * 64, "directory": "arm"},
            "tools": [f"arm-none-eabi-{name}" for name in ("ar", "gcc", "ld", "nm", "objcopy", "size")],
            "runtime_policy": {"gcc-runtime": {
                "license_expression": "GPL-3.0-or-later WITH GCC-exception-3.1",
                "source_repository": "https://example.invalid/gcc.git", "source_commit": "b" * 40,
                "license_url": "https://example.invalid/COPYING.RUNTIME", "license_file": "gcc-runtime.txt",
                "license_sha256": "c" * 64}}
        }))
        self.evidence = self.base / "evidence.json"
        self.write_evidence()

    def tearDown(self):
        self.temp.cleanup()

    def write_evidence(self, **changes):
        item = {"path": "lib/libgcc.a", "sha256": hashlib.sha256(self.runtime.read_bytes()).hexdigest(),
                "component": "gcc-runtime", "license_expression": "GPL-3.0-or-later WITH GCC-exception-3.1"}
        item.update(changes)
        self.evidence.write_text(json.dumps({"schema": "brickwright/linked-runtime-evidence/v1", "artifacts": [item]}))

    def invoke(self, ok=True):
        result = subprocess.run([sys.executable, str(TOOL), "--lock", str(self.lock),
                                 "--toolchain-root", str(self.root), "--linked-runtime", str(self.evidence)],
                                text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr) if ok else self.assertNotEqual(0, result.returncode)
        return result

    def test_exact_runtime_evidence_passes(self):
        self.invoke()

    def test_hash_drift_and_escape_fail(self):
        self.runtime.write_bytes(b"changed")
        self.assertIn("SHA-256 mismatch", self.invoke(ok=False).stderr)
        self.write_evidence(path="../outside.a")
        self.assertIn("escapes", self.invoke(ok=False).stderr)

    def test_runtime_policy_is_separate_from_project_source_policy(self):
        self.write_evidence(license_expression="MIT")
        self.assertIn("does not match", self.invoke(ok=False).stderr)

    def test_licence_evidence_bytes_are_verified(self):
        licence_dir = self.base / "licences"
        licence_dir.mkdir()
        licence = licence_dir / "gcc-runtime.txt"
        licence.write_bytes(b"reviewed terms")
        lock = json.loads(self.lock.read_text())
        lock["runtime_policy"]["gcc-runtime"]["license_sha256"] = hashlib.sha256(licence.read_bytes()).hexdigest()
        self.lock.write_text(json.dumps(lock))
        result = subprocess.run([sys.executable, str(TOOL), "--lock", str(self.lock),
                                 "--license-dir", str(licence_dir)], text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        licence.write_bytes(b"altered")
        result = subprocess.run([sys.executable, str(TOOL), "--lock", str(self.lock),
                                 "--license-dir", str(licence_dir)], text=True, capture_output=True)
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
