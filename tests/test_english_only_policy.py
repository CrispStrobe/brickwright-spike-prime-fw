#!/usr/bin/env python3
"""Unit tests for the English-only tracked-source policy."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


CHECKER = Path(__file__).resolve().parents[1] / "tools" / "check_english_only.py"
SPEC = importlib.util.spec_from_file_location("check_english_only", CHECKER)
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class EnglishOnlyPolicyTest(unittest.TestCase):
    def test_accepts_english_and_non_cjk_symbols(self) -> None:
        self.assertEqual(POLICY.cjk_lines("English → telemetry\n"), [])

    def test_rejects_each_prohibited_script(self) -> None:
        text = "\n".join(
            (
                f"Han: {chr(0x6F22)}",
                f"Hiragana: {chr(0x3042)}",
                f"Katakana: {chr(0x30A2)}",
                f"Hangul: {chr(0xD55C)}",
            )
        )
        self.assertEqual([line for line, _ in POLICY.cjk_lines(text)], [1, 2, 3, 4])

    def test_third_party_exception_is_path_scoped(self) -> None:
        self.assertTrue(POLICY.is_third_party("third_party/vendor/source.c"))
        self.assertFalse(POLICY.is_third_party("docs/en/third_party.md"))
        self.assertFalse(POLICY.is_third_party("third_party_notes.md"))


if __name__ == "__main__":
    unittest.main()
