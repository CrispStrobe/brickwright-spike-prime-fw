# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "tools/materialize_source_closure.py"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class MaterializeSourceClosureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repository"
        (self.repository / "upstream").mkdir(parents=True)
        (self.repository / "upstream/source.c").write_bytes(b"source\n")
        (self.repository / "generated.h").write_bytes(b"generated\n")
        self.roots = self.repository / "roots.json"
        self.roots.write_text(json.dumps({"schema": 1, "roots": [
            {"name": "upstream", "path": "upstream"}
        ]}))
        self.manifest = self.repository / "manifest.json"
        self.manifest.write_text(json.dumps({
            "schema": 1,
            "files": [{"source_root": "upstream", "path": "source.c", "sha256": sha256(b"source\n")}],
            "generated_inputs": [{"path": "generated.h", "sha256": sha256(b"generated\n")}],
        }))
        self.destination = self.base / "closure"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            sys.executable, TOOL,
            "--repository", self.repository,
            "--roots", self.roots,
            "--manifest", self.manifest,
            "--destination", self.destination,
        ], text=True, capture_output=True)

    def test_copies_only_declared_and_generated_inputs(self) -> None:
        result = self.invoke()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"source\n", (self.destination / "upstream/source.c").read_bytes())
        self.assertEqual(b"generated\n", (self.destination / "generated.h").read_bytes())
        self.assertEqual(2, len([path for path in self.destination.rglob("*") if path.is_file()]))

    def test_rejects_hash_drift_and_nonempty_destination(self) -> None:
        (self.repository / "upstream/source.c").write_bytes(b"changed\n")
        self.assertNotEqual(0, self.invoke().returncode)
        self.destination.mkdir(exist_ok=True)
        (self.destination / "foreign").write_text("x")
        self.assertIn("not empty", self.invoke().stderr)


if __name__ == "__main__":
    unittest.main()
