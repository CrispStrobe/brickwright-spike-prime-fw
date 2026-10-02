#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise the retained formatter, including unsupported target geometries."""
from pathlib import Path
import subprocess
import tempfile
from make_simulation_littlefs_seed import ROOT, compile_formatter, geometry, reviewed_inputs


def main():
    driver, config = reviewed_inputs(ROOT)
    for bad_driver, bad_config in [
            (driver.replace('W25Q256_SECTOR_SIZE    4096u', 'W25Q256_SECTOR_SIZE    8192u'), config),
            (driver.replace('0x00100000u', '0x00200000u'), config),
            (driver, config.replace('CONFIG_FS_LITTLEFS_PROGRAM_SIZE_FACTOR=4',
                                    'CONFIG_FS_LITTLEFS_PROGRAM_SIZE_FACTOR=1'))]:
        assert (bad_driver, bad_config) != (driver, config), 'mutation was ineffective'
        try:
            geometry(bad_driver, bad_config)
        except ValueError:
            pass
        else:
            raise AssertionError('unsupported firmware geometry accepted')
    with tempfile.TemporaryDirectory(prefix='brickwright-lfs-test-') as directory:
        work = Path(directory)
        binary, values = compile_formatter(ROOT, work)
        def run(output, block_size='4096', count='7936'):
            return subprocess.run([str(binary), str(output), block_size, count],
                                  capture_output=True, text=True)
        first, second = work/'first.bin', work/'second.bin'
        for output in (first, second):
            result = run(output)
            assert result.returncode == 0, result.stderr
            assert 'read-only mount verified' in result.stdout
            assert output.stat().st_size == 8192
        assert first.read_bytes() == second.read_bytes(), 'formatter is not deterministic'
        for block_size, count in [('8192', '7936'), ('4096', '8192'),
                                  ('4096', '0'), ('4096', '-1'),
                                  ('4096', '4294967296'), ('4096', '7936x')]:
            output = work/'rejected.bin'
            assert run(output, block_size, count).returncode == 2
            assert not output.exists(), 'invalid geometry emitted a seed'
        old = first.read_bytes()
        assert run(first).returncode == 8
        assert first.read_bytes() == old, 'existing output was overwritten'
        assert values['OFFSET'] == 0x100000 and values['BLOCK_COUNT'] == 7936
    print('LittleFS seed: read-only empty mount, deterministic 8192-byte output, geometry rejection and overwrite protection passed')


if __name__ == '__main__':
    main()
