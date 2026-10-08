#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Host self-controls for the probe; actual guest qualification is separate."""
from pathlib import Path
import os
import resource
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    with tempfile.TemporaryDirectory(prefix='lump-probe-control-') as directory:
        root = Path(directory)
        (root / 'nuttx/fs').mkdir(parents=True)
        (root / 'nuttx/config.h').write_text(
            '#define CONFIG_BUILD_PROTECTED 1\n#define CONFIG_LEGO_LUMP 1\n'
            '#define CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK 1\n')
        (root / 'nuttx/fs/ioctl.h').write_text(
            '#ifndef TEST_NUTTX_IOCTL_H\n#define TEST_NUTTX_IOCTL_H\n'
            '#include <sys/ioctl.h>\n#undef _IOC\n'
            '#define _IOC(base,nr) ((base)|(nr))\n#endif\n')
        board = root / 'arch/board'; board.mkdir(parents=True)
        for name in ['board_lump.h', 'board_legoport.h']:
            (board / name).write_bytes((ROOT / 'boards/spike-prime-hub/include' / name).read_bytes())
        source = (ROOT / 'apps/port/lumpprobe.c').read_text()
        (root / 'test_lumpprobe.c').write_bytes((ROOT / 'apps/port/test_lumpprobe.c').read_bytes())
        (root / 'lumpprobe.h').write_bytes((ROOT / 'apps/port/lumpprobe.h').read_bytes())
        variants = {
            'baseline': None,
            'ignore-changed-output': ('memcmp(&session, &before, sizeof(session)) != 0',
                                      '((void)memcmp(&session, &before, sizeof(session)), false)'),
            'ignore-invalid-refusal': ('result != -1 || error != EFAULT', 'false'),
        }
        for name, mutation in variants.items():
            candidate = source
            if mutation:
                old, new = mutation
                assert candidate.count(old) == 1
                candidate = candidate.replace(old, new)
            (root / 'lumpprobe.c').write_text(candidate)
            executable = root / name
            subprocess.run([os.environ.get('CC','cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                            *shlex.split(os.environ.get('LUMP_TEST_CFLAGS','')),
                            '-I'+str(root), str(root / 'test_lumpprobe.c'),
                            '-o', str(executable)], check=True)
            result = subprocess.run([str(executable)], capture_output=True, text=True,
                                    timeout=10, preexec_fn=no_core)
            if mutation:
                assert result.returncode != 0 and 'Assertion' in result.stderr, (name,result.stderr)
            else:
                assert result.returncode == 0, result.stderr
            print(name + ': ' + ('DETECTED' if mutation else 'PASS (14 scenarios)'))


if __name__ == '__main__':
    main()
