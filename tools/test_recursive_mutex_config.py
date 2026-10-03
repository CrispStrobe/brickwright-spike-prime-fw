#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Verify firmware enables the actual NuttX recursive mutex implementation."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nuttx', type=Path, default=ROOT / 'nuttx')
    parser.add_argument('--config-only', action='store_true')
    args = parser.parse_args()
    for profile in ('simulation', 'simulation-hci', 'usbnsh'):
        config = ROOT / 'boards/spike-prime-hub/configs' / profile / 'defconfig'
        assert 'CONFIG_PTHREAD_MUTEX_TYPES=y' in config.read_text().splitlines(), config
    print('Firmware profiles enable recursive pthread mutex kinds')
    if args.config_only:
        return
    source = args.nuttx / 'libs/libc/pthread/pthread_mutexattr_settype.c'
    header = (args.nuttx / 'include/pthread.h').read_text()
    constants = {}
    for name in ('PTHREAD_MUTEX_NORMAL', 'PTHREAD_MUTEX_RECURSIVE'):
        constants[name] = re.search(r'^#define\s+' + name + r'\s+(\d+)\s*$', header, re.M).group(1)
    # Compile the entire licensed NuttX source at its original path. Only its
    # small attribute/header boundary is mocked; no behavior is reimplemented.
    with tempfile.TemporaryDirectory(prefix='bw-recursive-mutex-') as directory:
        temp = Path(directory)
        (temp / 'nuttx').mkdir()
        (temp / 'pthread.h').write_text(
            '/* SPDX-License-Identifier: BSD-3-Clause; synthetic test boundary */\n'
            '#define FAR\n#define OK 0\n'
            + ''.join('#define %s %s\n' % pair for pair in constants.items())
            + 'typedef struct { int type; } pthread_mutexattr_t;\n'
            + 'int pthread_mutexattr_settype(pthread_mutexattr_t *,int);\n')
        (temp / 'main.c').write_text(
            '/* SPDX-License-Identifier: BSD-3-Clause; synthetic regression */\n'
            '#include <assert.h>\n#include <errno.h>\n#include <pthread.h>\n'
            'int main(void) { pthread_mutexattr_t a={PTHREAD_MUTEX_NORMAL};\n'
            '#ifdef EXPECT_SUPPORTED\n'
            'assert(pthread_mutexattr_settype(&a,PTHREAD_MUTEX_RECURSIVE)==0);\n'
            'assert(a.type==PTHREAD_MUTEX_RECURSIVE);\n'
            '#else\n'
            'assert(pthread_mutexattr_settype(&a,PTHREAD_MUTEX_RECURSIVE)==ENOSYS);\n'
            'assert(a.type==PTHREAD_MUTEX_NORMAL);\n'
            '#endif\n'
            'assert(pthread_mutexattr_settype(&a,99)==EINVAL); return 0; }\n')
        for supported in (False, True):
            (temp / 'nuttx/config.h').write_text(
                '#define CONFIG_PTHREAD_MUTEX_TYPES 1\n' if supported else '')
            command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(temp)]
            if supported:
                command.append('-DEXPECT_SUPPORTED')
            binary = temp / 'test'
            subprocess.run(command + [str(source.resolve()), str(temp / 'main.c'), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
    print('Actual NuttX source: recursive kind accepted when enabled; disabled configuration returns ENOSYS')


if __name__ == '__main__':
    main()
