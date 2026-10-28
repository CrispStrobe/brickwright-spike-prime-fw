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


class MediumCustody(unittest.TestCase):
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
