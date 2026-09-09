# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
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
        self.assertFalse(self.destination.exists())
        self.destination.mkdir(exist_ok=True)
        (self.destination / "foreign").write_text("x")
        self.assertIn("not empty", self.invoke().stderr)

    def test_materializes_relative_symlink_and_rejects_escape(self) -> None:
        document=json.loads(self.manifest.read_text())
        document["generated_symlinks"]=[{"path":"alias","target":"upstream","target_type":"directory"}]
        self.manifest.write_text(json.dumps(document)); result=self.invoke()
        self.assertEqual(0,result.returncode,result.stderr)
        link=self.destination/"alias"; self.assertTrue(link.is_symlink())
        self.assertFalse(Path(link.readlink()).is_absolute()); self.assertEqual((self.destination/"upstream").resolve(),link.resolve())
        shutil.rmtree(self.destination)
        document["generated_symlinks"][0]["target"]="../outside"; self.manifest.write_text(json.dumps(document))
        self.assertIn("safe relative",self.invoke().stderr)

    def test_materializes_file_symlink_and_preflights_missing_target(self) -> None:
        document=json.loads(self.manifest.read_text())
        document["generated_symlinks"]=[{"path":"source-link.c","target":"upstream/source.c","target_type":"file"}]
        self.manifest.write_text(json.dumps(document)); result=self.invoke()
        self.assertEqual(0,result.returncode,result.stderr); self.assertEqual(b"source\n",(self.destination/"source-link.c").read_bytes())
        shutil.rmtree(self.destination); document["generated_symlinks"][0]["target"]="upstream/absent.c"; self.manifest.write_text(json.dumps(document)); result=self.invoke()
        self.assertNotEqual(0,result.returncode); self.assertFalse(self.destination.exists())

    def test_empty_directory_target_is_not_invented_during_preflight(self) -> None:
        document=json.loads(self.manifest.read_text()); document["generated_symlinks"]=[{"path":"empty-link","target":"unpopulated","target_type":"directory"}]; self.manifest.write_text(json.dumps(document))
        result=self.invoke(); self.assertNotEqual(0,result.returncode); self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
