# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "tools/compare_offline_builds.py"


class CompareOfflineBuildsTest(unittest.TestCase):
    def test_accepts_identical_and_rejects_different_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "a", root / "b"
            first.mkdir(); second.mkdir()
            (first / "image.bin").write_bytes(b"same")
            (second / "image.bin").write_bytes(b"same")
            manifest = root / "manifest.json"; manifest.write_text("{}\n")
            output = root / "evidence.json"
            command = [
                sys.executable, TOOL, "--run-a", first, "--run-b", second,
                "--artifact", "image.bin", "--source-manifest", manifest,
                "--container-image", "sha256:" + "1" * 64, "--output", output,
            ]
            self.assertEqual(0, subprocess.run(command, capture_output=True).returncode)
            self.assertEqual("identical", json.loads(output.read_text())["status"])
            (second / "image.bin").write_bytes(b"different")
            self.assertNotEqual(0, subprocess.run(command, capture_output=True).returncode)
            self.assertEqual("different", json.loads(output.read_text())["status"])

    def test_rejects_mutable_image_reference_and_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("a", "b"):
                (root / name).mkdir()
            manifest = root / "manifest"; manifest.write_text("x")
            base = [sys.executable, TOOL, "--run-a", root / "a", "--run-b", root / "b",
                    "--source-manifest", manifest, "--output", root / "out"]
            self.assertNotEqual(0, subprocess.run(
                [*base, "--artifact", "x", "--container-image", "latest"], capture_output=True
            ).returncode)
            self.assertNotEqual(0, subprocess.run(
                [*base, "--artifact", "x", "--container-image", "sha256:short"], capture_output=True
            ).returncode)
            self.assertNotEqual(0, subprocess.run(
                [*base, "--artifact", "../x", "--container-image", "sha256:" + "1" * 64],
                capture_output=True,
            ).returncode)

    def test_rejects_artifact_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.bin"; outside.write_bytes(b"same")
            for name in ("a", "b"):
                run = root / name; run.mkdir(); (run / "image.bin").symlink_to(outside)
            manifest = root / "manifest"; manifest.write_text("x")
            result = subprocess.run([
                sys.executable, TOOL, "--run-a", root / "a", "--run-b", root / "b",
                "--artifact", "image.bin", "--source-manifest", manifest,
                "--container-image", "sha256:" + "1" * 64, "--output", root / "out",
            ], text=True, capture_output=True)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("symlink escapes", result.stderr)


if __name__ == "__main__":
    unittest.main()
