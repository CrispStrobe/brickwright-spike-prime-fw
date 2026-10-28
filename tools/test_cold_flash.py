#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Host media-custody controls; these do not qualify ARM calibration."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'simulation/bluetooth-air'))
from cold_flash import SIZE,image_hashes,validate_medium
from stage_imu_calibration_topology import stage


class MediumCustody(unittest.TestCase):
    def test_aggregate_topology_preserves_paired_imu_and_nor(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'runtime'
            cpu=runtime/'platforms/cpus/stm32f4.repl';cpu.parent.mkdir(parents=True)
            original=('timer12: Timers.STM32_Timer @ sysbus 0x40001800\n'
                      '    -> nvic@43\n    frequency: 10000000\n    initialLimit: 0xFFFF\n\n'
                      'timer12:\n    0 -> gpioPortB#14@09\n    1 -> gpioPortB#15@09\n')
            cpu.write_text(original)
            output=root/'staged';stage(runtime,output)
            clock=(output/'stm32f4.repl').read_text()
            self.assertIn('Timers.STM32TLCClock',clock)
            self.assertIn('frequency: 96000000',clock)
            self.assertIn('display: display',clock)
            board=(output/'spike-prime.repl').read_text()
            self.assertIn('imu: SPIKEPrime.LSM6DS3TRC',board)
            self.assertIn('norFlash: SPIKEPrime.W25Q256JV',board)
            self.assertIn('display: SPI.TLC5955',board)
            receipt=json.loads((output/'topology-receipt.json').read_text())
            for name,identity in receipt['files'].items():
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),identity['stagedSha256'])
            with self.assertRaisesRegex(ValueError,'output exists'):stage(runtime,output)
            cpu.write_text(original.replace('10000000','12000000'))
            rejected=root/'rejected'
            with self.assertRaisesRegex(ValueError,'TIM12 declaration'):stage(runtime,rejected)
            self.assertFalse(rejected.exists())

    def test_exact_medium_and_image_pair_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);images=root/'images';images.mkdir()
            (images/'nuttx').write_bytes(b'synthetic kernel')
            (images/'nuttx_user.elf').write_bytes(b'synthetic userspace')
            medium=root/'medium.bin';medium.write_bytes(bytes(SIZE))
            receipt={'schema':1,'kind':'own-guest-calibration-medium','bytes':SIZE,
                     'sha256':hashlib.sha256(medium.read_bytes()).hexdigest(),**image_hashes(images)}
            sidecar=Path(str(medium)+'.json')
            sidecar.write_text(json.dumps(receipt))
            self.assertEqual(validate_medium(medium,images),receipt)
            for patch in ({'schema':True},{'unknown':1},{'sha256':'0'*64},
                          {'kernelSha256':'0'*64},{'userspaceSha256':'0'*64}):
                sidecar.write_text(json.dumps({**receipt,**patch}))
                with self.assertRaisesRegex(ValueError,'identity mismatch'):
                    validate_medium(medium,images)
            sidecar.write_text(json.dumps(receipt))
            sidecar.write_text('[]')
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                validate_medium(medium,images)
            sidecar.write_text(' '*4097)
            with self.assertRaisesRegex(ValueError,'bounded identity'):
                validate_medium(medium,images)
            sidecar.write_text(json.dumps(receipt))
            with medium.open('r+b') as output:output.seek(SIZE-1);output.write(b'\x01')
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                validate_medium(medium,images)
            medium.write_bytes(b'truncated')
            with self.assertRaisesRegex(ValueError,'complete'):
                validate_medium(medium,images)
            alias=root/'alias';alias.symlink_to(medium)
            with self.assertRaisesRegex(ValueError,'regular'):
                validate_medium(alias,images)


if __name__=='__main__':unittest.main()
