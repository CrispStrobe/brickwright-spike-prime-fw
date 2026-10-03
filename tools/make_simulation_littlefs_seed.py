#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Format a private empty-flash prefix with the reviewed retained LittleFS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DRIVER = 'boards/spike-prime-hub/src/stm32_w25q256.c'
LFS = 'nuttx/fs/littlefs/littlefs'


def reviewed_inputs(root):
    policy = json.loads((root / 'policy/simulation-firmware-inputs.json').read_text())
    expected = {item['path']: item['sha256'] for item in policy['files']}
    for name in [DRIVER, 'nuttx/fs/littlefs/lfs_vfs.c',
                 *[f'{LFS}/{name}' for name in ('lfs.c', 'lfs.h', 'lfs_util.c', 'lfs_util.h')]]:
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != expected[name]:
            raise ValueError(f'unreviewed formatter input: {name}')
    config = (root / 'nuttx/.config').read_bytes()
    if hashlib.sha256(config).hexdigest() != policy['config_sha256']:
        raise ValueError('unreviewed firmware configuration')
    return (root / DRIVER).read_text(), config.decode()


def geometry(driver, config):
    # Fail closed on changes to the board's public MTD layout. The partition,
    # not the complete chip, is passed to the retained LittleFS VFS.
    macros = dict(re.findall(r'^#define\s+(W25Q256_\w+)\s+(.+?)\s*(?:/\*.*)?$', driver, re.M))
    expected = {
        'W25Q256_PAGE_SIZE': '256u', 'W25Q256_SECTOR_SIZE': '4096u',
        'W25Q256_CHIP_SIZE': '(32u * 1024u * 1024u)',
        'W25Q256_RESERVED_BYTES': '0x00100000u',
        'W25Q256_NSECTORS': '(W25Q256_CHIP_SIZE / W25Q256_SECTOR_SIZE)',
        'W25Q256_FS_START_SECTOR': '(W25Q256_RESERVED_BYTES / W25Q256_SECTOR_SIZE)',
        'W25Q256_FS_NSECTORS': '(W25Q256_NSECTORS - W25Q256_FS_START_SECTOR)',
    }
    for name, value in expected.items():
        if macros.get(name) != value:
            raise ValueError(f'unsupported board geometry: {name}')
    options = dict(re.findall(r'^CONFIG_FS_LITTLEFS_(\w+)=(.+)$', config, re.M))
    expected_options = {
        'PROGRAM_SIZE_FACTOR': '4', 'READ_SIZE_FACTOR': '4',
        'BLOCK_SIZE_FACTOR': '1', 'CACHE_SIZE_FACTOR': '4',
        'LOOKAHEAD_SIZE': '0', 'BLOCK_CYCLE': '200', 'NAME_MAX': '32',
        'FILE_MAX': '2147483647', 'ATTR_MAX': '1022', 'VERSION': '"v2.5.1"',
    }
    for name, value in expected_options.items():
        if options.get(name) != value:
            raise ValueError(f'unsupported LittleFS configuration: {name}')
    if 'CONFIG_FS_LITTLEFS_MULTI_VERSION=y' in config:
        raise ValueError('unsupported LittleFS multi-version configuration')
    return dict(OFFSET=0x100000, BLOCK_SIZE=4096, BLOCK_COUNT=(32*1024*1024-0x100000)//4096,
                READ_SIZE=256*4, PROG_SIZE=256*4, CACHE_SIZE=256*4,
                LOOKAHEAD_SIZE=(((7936+63)//64)*64)//8,
                BLOCK_CYCLES=200, NAME_MAX=32, FILE_MAX=2147483647, ATTR_MAX=1022)


def compile_formatter(root, work):
    values = geometry(*reviewed_inputs(root))
    (work / 'simulation_littlefs_geometry.h').write_text(''.join(
        f'#define BW_LFS_{name} {value}u\n' for name, value in values.items()))
    binary = work / 'format-littlefs'
    common = [os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-Wall', '-Wextra',
              '-Werror', '-DLFS_NO_MALLOC', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN',
              '-DLFS_NO_ERROR', '-I'+str(work), '-I'+str(root / LFS)]
    objects = []
    for name, source, retained in [
            ('formatter', root / 'tools/format_simulation_littlefs.c', False),
            ('lfs', root / LFS / 'lfs.c', True),
            ('lfs_util', root / LFS / 'lfs_util.c', True)]:
        obj = work / (name+'.o')
        # The pinned NuttX LittleFS getpath patch has signedness warnings;
        # preserve its reviewed bytes and keep authored code under -Werror.
        extra = ['-Wno-error=sign-compare'] if retained else []
        subprocess.run(common+extra+['-c', str(source), '-o', str(obj)], check=True)
        objects.append(str(obj))
    subprocess.run([common[0], *objects, '-o', str(binary)], check=True)
    return binary, values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new private output file; never overwrites existing files')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists')
    with tempfile.TemporaryDirectory(prefix='brickwright-lfs-') as directory:
        binary, values = compile_formatter(ROOT, Path(directory))
        subprocess.run([str(binary), str(args.output.resolve()), str(values['BLOCK_SIZE']),
                        str(values['BLOCK_COUNT'])], check=True)
    print('seed sha256:', hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
