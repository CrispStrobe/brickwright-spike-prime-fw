# SPDX-License-Identifier: Apache-2.0
"""Tests for the configured-build symlink boundary."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "tools/check_build_tree_links.py"


class BuildTreeLinksTest(unittest.TestCase):
    def test_accepts_internal_relative_and_absolute_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tree").mkdir()
            (root / "target").write_text("ok", encoding="utf-8")
            (root / "tree/relative").symlink_to("../target")
            (root / "tree/absolute").symlink_to(root / "target")
            result = self.invoke(root)
            self.assertEqual(0, result.returncode, result.stdout)

    def test_rejects_escape_without_printing_external_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            outside = Path(temporary) / "other-worktree"
            (root / "tree").mkdir(parents=True)
            outside.mkdir()
            (root / "tree/board").symlink_to(outside)
            result = self.invoke(root)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("tree/board", result.stdout)
            self.assertNotIn(str(outside), result.stdout)

    @staticmethod
    def invoke(root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), "--repository", str(root), "--tree", "tree"],
            text=True,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
