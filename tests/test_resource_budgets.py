# SPDX-License-Identifier: MIT

import tempfile
import unittest
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.check_resource_budgets import (
    BudgetError,
    check_configuration,
    parse_defines,
    parse_nm_symbol_size,
    parse_nm_symbol_value,
    parse_size,
    run,
)


class ResourceBudgetTests(unittest.TestCase):
    def test_size_accounts_for_flash_load_and_static_ram(self):
        output = "text data bss dec hex filename\n500232 14984 75560 590776 903b8 image\n"
        self.assertEqual(parse_size(output), (515216, 90544))

    def test_size_rejects_unparseable_output(self):
        with self.assertRaises(BudgetError):
            parse_size("nothing useful")

    def test_payload_symbol_must_be_unique_and_exactly_sized(self):
        output = "08090000 000027e3 r brickwright_local_ti_bts_image\n"
        self.assertEqual(
            parse_nm_symbol_size(output, "brickwright_local_ti_bts_image"), 10211
        )
        with self.assertRaises(BudgetError):
            parse_nm_symbol_size("", "brickwright_local_ti_bts_image")

    def test_symbol_value_accepts_sized_and_absolute_nm_rows(self):
        output = "20020000 A _sdata\n200248a4 00000420 D pools\n"
        self.assertEqual(parse_nm_symbol_value(output, "_sdata"), 0x20020000)
        self.assertEqual(parse_nm_symbol_value(output, "pools"), 0x200248A4)
        with self.assertRaises(BudgetError):
            parse_nm_symbol_value(output, "missing")

    def test_configuration_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").write_text("CONFIG_STACK=4096\n", encoding="utf-8")
            limits = {"config": {"CONFIG_STACK": {"min": 2048, "max": 8192}}}
            self.assertEqual(check_configuration(root, limits)[0].split()[0], "CONFIG_STACK=4096")
            limits["config"]["CONFIG_STACK"]["max"] = 2048
            with self.assertRaises(BudgetError):
                check_configuration(root, limits)

    def test_parses_header_and_dot_config_numbers(self):
        values = parse_defines("#define CONFIG_A 0x10\nCONFIG_B=32\n")
        self.assertEqual(values, {"CONFIG_A": 16, "CONFIG_B": 32})

    def test_complete_gate_accepts_reviewed_image_and_rejects_flash_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "image.elf").write_bytes(b"ELF")
            (root / "config").write_text("CONFIG_STACK=4096\n", encoding="utf-8")
            policy_path = root / "policy.json"
            policy = {
                "schema": 1,
                "protected_userspace": {
                    "flash_bytes_max": 110,
                    "static_ram_bytes_max": 50,
                    "ti_payload_symbol": "payload",
                    "ti_payload_bytes_exact": 10211,
                },
                "configuration": {
                    "config": {"CONFIG_STACK": {"min": 4096, "max": 4096}}
                },
            }
            import json
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            arguments = Namespace(
                root=root, policy="policy.json", elf="image.elf",
                size_tool="size", nm_tool="nm",
            )
            completed = [
                unittest.mock.Mock(stdout="100 10 20 130 82 image.elf\n"),
                unittest.mock.Mock(stdout=(
                    "08090000 000027e3 r payload\n"
                    "20020000 A _sdata\n"
                    "20021000 A __start_net_buf_pool\n"
                    "20021100 A __stop_net_buf_pool\n"
                    "20022000 A _edata\n"
                )),
            ]
            with patch("tools.check_resource_budgets.subprocess.run", side_effect=completed):
                self.assertIn("userspace flash=110/110 bytes", run(arguments))
            policy["protected_userspace"]["flash_bytes_max"] = 109
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            with patch("tools.check_resource_budgets.subprocess.run", return_value=completed[0]):
                with self.assertRaises(BudgetError):
                    run(arguments)


if __name__ == "__main__":
    unittest.main()
