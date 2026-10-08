#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile the engine's actual DATA queue, including hostile session schedules."""
from pathlib import Path
import os
import resource
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'boards/spike-prime-hub/src/lump_data_queue.h'
MUTATIONS = {
    'reuse-session': ('q->session++;', 'q->session = 1;'),
    'retain-old-frames': ('q->head = q->tail = q->count = 0;', '/* stale queue retained */'),
    'admit-unsynchronized-data': ('if (!q->active)\n', 'if (false)\n'),
    'publish-wrong-session': ('out->session = q->session;', 'out->session = q->session + 1;'),
    'wrap-session': ('if (q->session == UINT64_MAX)', 'if (false)'),
}


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    with tempfile.TemporaryDirectory(prefix='lump-session-') as directory:
        root = Path(directory)
        board = root / 'arch/board'
        board.mkdir(parents=True)
        (board / 'board_lump.h').write_bytes(
            (ROOT / 'boards/spike-prime-hub/include/board_lump.h').read_bytes())
        original = SOURCE.read_text()
        for name, mutation in [('baseline', None), *MUTATIONS.items()]:
            source = original
            if mutation:
                before, after = mutation
                assert source.count(before) == 1, name
                source = source.replace(before, after)
            (root / 'lump_data_queue.h').write_text(source)
            executable = root / name
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11',
                            '-Wall', '-Wextra', '-Werror', '-pthread',
                            *shlex.split(os.environ.get('LUMP_TEST_CFLAGS', '')),
                            '-I' + str(root),
                            str(ROOT / 'boards/spike-prime-hub/test/test_lump_data_queue.c'),
                            '-o', str(executable)], check=True)
            result = subprocess.run([str(executable)], capture_output=True,
                                    text=True, timeout=10, preexec_fn=no_core)
            if mutation:
                assert result.returncode != 0 and 'Assertion' in result.stderr, name
            else:
                assert result.returncode == 0, result.stderr
            print(name + ': ' + ('DETECTED' if mutation else 'PASS'))


if __name__ == '__main__':
    main()
