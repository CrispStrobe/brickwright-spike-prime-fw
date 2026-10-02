#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Crash/restart tests with the build's external LittleFS sources (no download)."""
import argparse
import hashlib
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

def function(text, signature):
    start = text.index(signature)
    end = text.index('{', start)
    depth = 1
    end += 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('littlefs', type=pathlib.Path,
                        help='qualified nuttx/fs/littlefs/littlefs directory')
    args = parser.parse_args()
    source = args.littlefs.resolve()
    for name in ('lfs.c', 'lfs.h', 'lfs_util.c', 'lfs_util.h', 'LICENSE.md'):
        data = (source / name).read_bytes()
        print(f'{name}: sha256={hashlib.sha256(data).hexdigest()}', flush=True)
    board = (ROOT / 'boards/spike-prime-hub/src/stm32_w25q256.c').read_text()
    with tempfile.TemporaryDirectory(prefix='bw-lfs-crash-') as temp:
        generated = pathlib.Path(temp) / 'board_policy.h'
        (pathlib.Path(temp) / 'nuttx/mm').mkdir(parents=True)
        (pathlib.Path(temp) / 'nuttx/mm/mm.h').write_text('/* Host allocator shim. */\n')
        (pathlib.Path(temp) / 'fs_heap.h').write_text('#include <stdlib.h>\n#define fs_heap_malloc malloc\n#define fs_heap_free free\n')
        generated.write_text(board[:board.index('*/') + 2] + '\n' +
                             '\n'.join(function(board, signature) for signature in (
            'static int w25q256_partition_erased(', 'static int w25q256_mount(')))
        binary = pathlib.Path(temp) / 'test'
        subprocess.run(['cc', '-std=c99', '-O1', '-Wall', '-Wextra', '-Werror',
                        '-Wno-sign-compare', '-D_DEFAULT_SOURCE', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN',
                        '-DLFS_NO_ERROR', '-I' + str(source), '-I' + temp,
                        str(ROOT / 'apps/hubprogram/test/littlefs_power_loss_test.c'),
                        str(ROOT / 'apps/hubprogram/program.c'),
                        str(ROOT / 'apps/hubprogram/upload.c'),
                        str(source / 'lfs.c'), str(source / 'lfs_util.c'),
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)

if __name__ == '__main__':
    main()
