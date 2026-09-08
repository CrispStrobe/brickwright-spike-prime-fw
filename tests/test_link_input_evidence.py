# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/link_input_evidence.py"


class LinkInputEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "arm"; (self.root / "bin").mkdir(parents=True)
        shutil.copy2(shutil.which("ar"), self.root / "bin" / "arm-none-eabi-ar")
        runtime = self.root / "lib"; runtime.mkdir()
        (self.base / "one.o").write_bytes(b"one")
        (self.base / "two.o").write_bytes(b"two")
        subprocess.run([self.root / "bin" / "arm-none-eabi-ar", "rc", runtime / "libgcc.a",
                        self.base / "one.o", self.base / "two.o"], check=True)
        (runtime / "crt0.o").write_bytes(b"startup")
        self.lock = self.base / "lock.json"
        self.lock.write_text(json.dumps({"runtime_policy": {
            "gcc-runtime": {"license_expression": "GPL-3.0-or-later WITH GCC-exception-3.1"},
            "newlib": {"license_expression": "LicenseRef-Newlib-Notice-Collection"}}}))
        self.declarations = self.base / "inputs.json"
        self.declarations.write_text(json.dumps({"schema": "brickwright/runtime-input-declaration/v1", "artifacts": [
            {"path": "lib/libgcc.a", "component": "gcc-runtime"},
            {"path": "lib/crt0.o", "component": "newlib"}]}))
        self.map = self.base / "firmware.map"
        self.map.write_text(f"LOAD {runtime / 'crt0.o'}\n {runtime / 'libgcc.a'}(one.o)\n")
        (self.base / "link.rsp").write_text(f"-Map={self.map} {runtime / 'libgcc.a'} {runtime / 'crt0.o'}")
        self.argv = self.base / "argv.json"; self.argv.write_text('["arm-none-eabi-ld","@link.rsp"]')
        self.output = self.base / "evidence.json"

    def tearDown(self): self.temporary.cleanup()

    def invoke(self, ok=True):
        result = subprocess.run([sys.executable, TOOL, "--lock", self.lock,
            "--toolchain-root", self.root, "--declarations", self.declarations,
            "--link-argv", self.argv, "--link-cwd", self.base,
            "--map", self.map, "--output", self.output],
            text=True, capture_output=True)
        if ok and result.returncode: self.fail(result.stderr)
        if not ok and not result.returncode: self.fail("unexpected success")
        return result

    def test_exact_map_selection_and_member_hashes_are_deterministic(self):
        self.invoke(); first = self.output.read_bytes(); self.invoke()
        self.assertEqual(first, self.output.read_bytes())
        evidence = json.loads(first)
        self.assertEqual("brickwright/linked-runtime-evidence/v1", evidence["schema"])
        archive = next(x for x in evidence["artifacts"] if x["path"].endswith("libgcc.a"))
        self.assertEqual(["one.o"], [x["path"] for x in archive["selected_members"]])
        self.assertEqual(["firmware.map"], evidence["link_argv_cross_check"]["map_outputs"])

    def test_argv_map_disagreement_fails_closed(self):
        (self.base / "link.rsp").write_text(f"-Map=other.map {self.root / 'lib/libgcc.a'}")
        self.assertIn("does not name captured maps", self.invoke(ok=False).stderr)

    def test_undeclared_and_stale_artifacts_fail_closed(self):
        data = json.loads(self.declarations.read_text()); data["artifacts"].pop()
        self.declarations.write_text(json.dumps(data))
        self.assertIn("undeclared", self.invoke(ok=False).stderr)
        data["artifacts"].append({"path": "lib/crt0.o", "component": "newlib"})
        self.declarations.write_text(json.dumps(data))
        self.map.write_text(f" {self.root / 'lib/libgcc.a'}(one.o)\n")
        self.assertIn("stale", self.invoke(ok=False).stderr)

    def test_missing_and_duplicate_archive_members_fail(self):
        self.map.write_text(f"LOAD {self.root / 'lib/crt0.o'}\n {self.root / 'lib/libgcc.a'}(missing.o)\n")
        self.assertIn("not unique", self.invoke(ok=False).stderr)

    def test_unknown_component_and_escaping_path_fail(self):
        data = json.loads(self.declarations.read_text()); data["artifacts"][0]["component"] = "guessed"
        self.declarations.write_text(json.dumps(data))
        self.assertIn("unknown reviewed component", self.invoke(ok=False).stderr)
        data["artifacts"][0] = {"path": "../escape.a", "component": "gcc-runtime"}
        self.declarations.write_text(json.dumps(data))
        self.assertIn("escapes toolchain", self.invoke(ok=False).stderr)


if __name__ == "__main__": unittest.main()
