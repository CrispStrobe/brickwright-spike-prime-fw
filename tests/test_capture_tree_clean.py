# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "tools/check_capture_tree_clean.py"


class CaptureTreeCleanTest(unittest.TestCase):
    def test_accepts_source_only_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tree").mkdir()
            (root / "tree/source.c").write_text("source\n")
            result = self.invoke(root)
            self.assertEqual(0, result.returncode, result.stdout)

    def test_rejects_residual_without_host_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tree/lib").mkdir(parents=True)
            (root / "tree/lib/stale.o").write_bytes(b"stale")
            result = self.invoke(root)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("tree/lib/stale.o", result.stdout)
            self.assertNotIn(str(root), result.stdout)

    def test_allows_explicit_tracked_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tree").mkdir()
            (root / "tree/fixture.d").write_text("tracked fixture\n")
            result = subprocess.run(
                [sys.executable, TOOL, "--repository", root, "--tree", "tree",
                 "--allow", "tree/fixture.d"],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, result.returncode, result.stdout)

    @staticmethod
    def invoke(root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, TOOL, "--repository", root, "--tree", "tree"],
            text=True,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
