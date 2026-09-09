# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/audit_build_capture.py"


class CaptureAuditTest(unittest.TestCase):
    def test_reports_insufficient_capture_as_structured_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trace = root / "trace"
            trace.write_text('1 openat(9, "source.c", O_RDONLY) = 3\n')
            result = subprocess.run(
                [sys.executable, TOOL, "--trace", trace, "--cwd", root, "--tree", root],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(0, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual("incomplete", report["status"])
            self.assertEqual(3, len(report["errors"]))
            self.assertIn("unresolved dirfd", report["errors"][0])
            self.assertEqual("$TREE", report["capture"]["initial_cwd"])
            self.assertNotIn(str(root), result.stdout)

    def test_rejects_successful_network_connection_without_endpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "one.d").write_text("one.o: one.c\n")
            (root / "two.d").write_text("two.o: two.c\n")
            (root / "firmware.map").write_text("map\n")
            trace = root / "trace"
            trace.write_text(
                '7 connect(3, {sa_family=AF_INET, sin_port=htons(443)}, 16) = 0\n'
            )
            result = subprocess.run(
                [sys.executable, TOOL, "--trace", trace, "--cwd", root, "--tree", root],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(0, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual(1, report["network_connect_attempt_count"])
            self.assertEqual(1, report["successful_network_connect_count"])
            self.assertNotIn("443", result.stdout)

    def test_external_non_file_identity_does_not_expose_host_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            tree = base / "tree"
            tree.mkdir()
            (tree / "one.d").write_text("one.o: one.c\n")
            (tree / "two.d").write_text("two.o: two.c\n")
            (tree / "firmware.map").write_text("map\n")
            trace = tree / "trace"
            trace.write_text('1 openat(AT_FDCWD, "/dev/null", O_RDONLY) = 3\n')
            result = subprocess.run(
                [sys.executable, TOOL, "--trace", trace, "--cwd", tree, "--tree", tree,
                 "--link-provenance-error", "archive member lacks compiler producer"],
                text=True,
                capture_output=True,
            )
            report = json.loads(result.stdout)
            self.assertEqual("character-device", report["non_file_paths"][0]["kind"])
            self.assertTrue(report["non_file_paths"][0]["path"].startswith("$EXTERNAL/path-"))
            self.assertNotIn(str(base), result.stdout)
            self.assertNotIn("/dev/null", result.stdout)
            self.assertEqual("trace-ready", report["status"])
            self.assertEqual("trace-path-and-network-coverage-only", report["scope"])
            self.assertEqual("invalid", report["link_provenance"]["status"])

    def test_missing_paths_are_stable_and_host_path_free(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            tree = base / "tree"; tree.mkdir()
            for name in ("one.d", "two.d"): (tree / name).write_text("x: y\n")
            (tree / "firmware.map").write_text("map\n")
            internal = tree / "generated/missing.o"
            external = base / "host-secret/missing.o"
            trace = tree / "trace"
            trace.write_text(
                f'1 openat(AT_FDCWD, "{internal}", O_RDONLY) = 3\n'
                f'1 openat(AT_FDCWD, "{external}", O_RDONLY) = 4\n'
            )
            result = subprocess.run(
                [sys.executable, TOOL, "--trace", trace, "--cwd", tree, "--tree", tree],
                text=True, capture_output=True,
            )
            self.assertNotEqual(0, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual(2, report["missing_path_count"])
            self.assertEqual("$TREE/generated/missing.o", report["missing_paths"][1])
            self.assertTrue(report["missing_paths"][0].startswith("$EXTERNAL/path-"))
            self.assertNotIn(str(base), result.stdout)
            second = subprocess.run(
                [sys.executable, TOOL, "--trace", trace, "--cwd", tree, "--tree", tree],
                text=True, capture_output=True,
            )
            self.assertEqual(report["missing_paths"], json.loads(second.stdout)["missing_paths"])


if __name__ == "__main__":
    unittest.main()
