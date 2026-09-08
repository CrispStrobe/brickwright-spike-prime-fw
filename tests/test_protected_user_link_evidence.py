# SPDX-License-Identifier: Apache-2.0
"""Guard the protected userspace link-evidence contract."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProtectedUserLinkEvidenceTest(unittest.TestCase):
    def test_linker_emits_a_real_userspace_map(self) -> None:
        makefile = (ROOT / "boards/spike-prime-hub/kernel/Makefile").read_text(
            encoding="utf-8"
        )
        self.assertIn("USER_LINKMAP =", makefile)
        self.assertIn("-Map=$(USER_LINKMAP)", makefile)

    def test_symbol_listing_remains_distinct_from_link_map(self) -> None:
        makefile = (ROOT / "boards/spike-prime-hub/kernel/Makefile").read_text(
            encoding="utf-8"
        )
        self.assertIn("$(NM) nuttx_user.elf >$(TOPDIR)$(DELIM)User.map", makefile)
        self.assertNotIn("USER_LINKMAP = $(TOPDIR)$(DELIM)User.map", makefile)


if __name__ == "__main__":
    unittest.main()
