#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The TI-free image gate finds embedded chunks at any offset and alignment.

The fixtures are random bytes standing in for a service pack; no TI bytes are
used. Each case is driven so the gate's verdict depends on the property named.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_ti_free_image.py"
sys.path.insert(0, str(ROOT / "tools"))
import check_ti_free_image as gate  # noqa: E402


class TiFreeImageGate(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.pack = os.urandom(10211)  # same shape as the real pack: 39 chunks + tail
        (self.root / "pack.bts").write_bytes(self.pack)
        self.fingerprint = self.root / "fingerprint.json"
        subprocess.run([sys.executable, str(TOOL), "--write-fingerprint",
                        "--bts", str(self.root / "pack.bts"),
                        "--fingerprint", str(self.fingerprint)],
                       check=True, stdout=subprocess.DEVNULL)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def run_gate(self, image: bytes, *extra: str) -> subprocess.CompletedProcess:
        path = self.root / "image.bin"
        path.write_bytes(image)
        return subprocess.run([sys.executable, str(TOOL), str(path),
                               "--fingerprint", str(self.fingerprint), *extra],
                              text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)

    def test_fingerprint_contains_no_pack_bytes(self) -> None:
        text = self.fingerprint.read_text()
        document = json.loads(text)
        self.assertEqual(len(document["chunks"]), 40)
        # Only digests are stored: no 4-byte run of the pack appears in hex.
        for offset in range(0, len(self.pack) - 4):
            self.assertNotIn(self.pack[offset:offset + 4].hex(), text)

    def test_clean_image_passes(self) -> None:
        result = self.run_gate(os.urandom(200_000))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("0/40 service-pack chunks present", result.stdout)

    def test_embedded_at_unaligned_offset_fails_with_every_chunk(self) -> None:
        image = os.urandom(12_345) + self.pack + os.urandom(999)
        result = self.run_gate(image)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("40/40 service-pack chunks present", result.stdout)
        self.assertIn("offset 0x3039", result.stdout)

    def test_partial_copy_is_counted(self) -> None:
        # Bytes [256, 1280) hold exactly chunks 1..4.
        image = os.urandom(777) + self.pack[256:1280] + os.urandom(777)
        result = self.run_gate(image)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("4/40 service-pack chunks present", result.stdout)

    def test_stale_fingerprint_is_rejected(self) -> None:
        other = self.root / "other.bts"
        other.write_bytes(os.urandom(len(self.pack)))
        result = self.run_gate(os.urandom(4096), "--bts", str(other))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("fingerprint does not match", result.stdout)

    def test_build_log_reference_fails(self) -> None:
        log = self.root / "build.log"
        log.write_text("python3 tools/import_ti_service_pack.py --from-ti\n")
        result = self.run_gate(os.urandom(4096), "--build-log", str(log))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("import_ti_service_pack", result.stdout)
        log.write_text("CC: ti_bts_loader.c hci_driver.c\n")
        result = self.run_gate(os.urandom(4096), "--build-log", str(log))
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_config_must_select_simulation_profile(self) -> None:
        config = self.root / ".config"
        config.write_text("CONFIG_APP_BTSENSOR=y\n")
        result = self.run_gate(os.urandom(4096), "--config", str(config))
        self.assertEqual(result.returncode, 1, result.stdout)
        config.write_text(f"{gate.SIM_OPTION}=y\n")
        result = self.run_gate(os.urandom(4096), "--config", str(config))
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_committed_fingerprint_is_well_formed(self) -> None:
        document = gate.load_fingerprint(gate.DEFAULT_FINGERPRINT)
        self.assertEqual(
            document["service_pack_sha256"],
            "646723c01de351eaf9c6b6b33f4f0dac9567b948a2e93daed9da7a896b6e1b0e")
        self.assertEqual(len(document["chunks"]), 40)

    def test_elf_check_falls_back_to_host_nm(self) -> None:
        elf = self.root / "image.elf"
        elf.write_bytes(b"synthetic")
        with mock.patch.object(gate.shutil, "which",
                               side_effect=lambda name: None if name != "nm" else "/usr/bin/nm"), \
             mock.patch.object(gate.subprocess, "run") as run:
            run.return_value.stdout = "08000000 T clean_symbol\n"
            self.assertFalse(gate.elf_defines(elf, gate.PAYLOAD_SYMBOL))
            run.assert_called_once_with(
                ["/usr/bin/nm", str(elf)], check=True, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def test_elf_check_fails_closed_without_nm(self) -> None:
        elf = self.root / "image.elf"
        elf.write_bytes(b"synthetic")
        with mock.patch.object(gate.shutil, "which", return_value=None):
            with self.assertRaisesRegex(SystemExit, "no nm implementation found"):
                gate.elf_defines(elf, gate.PAYLOAD_SYMBOL)


if __name__ == "__main__":
    unittest.main()
