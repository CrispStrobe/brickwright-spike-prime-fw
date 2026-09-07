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


if __name__ == "__main__":
    unittest.main()
