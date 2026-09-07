import importlib.util
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "tools" / "check_live_docs.py"
SPEC = importlib.util.spec_from_file_location("check_live_docs", CHECKER)
assert SPEC and SPEC.loader
check_live_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_live_docs)


class LiveDocsPolicyTests(unittest.TestCase):
    def make_tree(self, replacement: str | None = None) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in check_live_docs.LIVE_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Current contract.\n", encoding="utf-8")
        if replacement is not None:
            (root / "PLAN.md").write_text(replacement, encoding="utf-8")
        return root

    def test_accepts_current_documents(self):
        self.assertEqual(check_live_docs.check(self.make_tree()), [])

    def test_rejects_completion_marker(self):
        errors = check_live_docs.check(self.make_tree("- [x] old task\n"))
        self.assertTrue(any("completed/in-progress marker" in e for e in errors))

    def test_rejects_checkpoint_log(self):
        errors = check_live_docs.check(self.make_tree("## Checkpoint log\n"))
        self.assertTrue(any("checkpoint log" in e for e in errors))

    def test_rejects_obsolete_ti_claim(self):
        errors = check_live_docs.check(
            self.make_tree("The CC2564C used a v1.4 payload.\n")
        )
        self.assertTrue(any("obsolete CC2564C v1.4" in e for e in errors))

    def test_rejects_ehci_payload_patch(self):
        errors = check_live_docs.check(
            self.make_tree("Patch the eHCILL byte in the payload.\n")
        )
        self.assertTrue(any("modified eHCILL" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
