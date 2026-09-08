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


if __name__ == "__main__":
    unittest.main()
