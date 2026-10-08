#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile the unchanged actual boot registration function with faulting services.

This is a host control, not NuttX thread or partial-boot qualification. The
engine representation and OS services are neutral test doubles; registration
code is copied byte-for-byte from the retained driver, never reimplemented.
"""
from pathlib import Path
import os
import resource
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'boards/spike-prime-hub/src/stm32_legoport_lump.c'
START = 'int stm32_legoport_lump_register(void)\n{'
END = '\n#endif /* CONFIG_LEGO_LUMP */'


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    driver = DRIVER.read_text()
    assert driver.count(START) == driver.count(END) == 1
    function = driver.split(START)[1].split(END)[0]
    original = START + function
    assert original.rstrip().endswith('}')
    mutations = {
        'retry-live-engines': ('if (g_lump_registration_started)', 'if (false)'),
        'late-started-flag': (
            'g_lump_registration_started = true;',
            '/* incorrectly delayed until all services succeed */'),
    }
    with tempfile.TemporaryDirectory(prefix='lump-registration-') as directory:
        root = Path(directory)
        for name, mutation in [('baseline', None), *mutations.items()]:
            source = original
            if mutation:
                before, after = mutation
                assert source.count(before) == 1, name
                source = source.replace(before, after)
                if name == 'late-started-flag':
                    before = '  return OK;'
                    assert source.count(before) == 1
                    source = source.replace(before,
                        '  g_lump_registration_started = true;\n' + before)
            (root / 'registration.inc').write_text(source)
            executable = root / name
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11',
                            '-Wall', '-Wextra', '-Werror',
                            *shlex.split(os.environ.get('LUMP_TEST_CFLAGS', '')),
                            '-I' + str(root),
                            str(ROOT / 'boards/spike-prime-hub/test/test_lump_registration.c'),
                            '-o', str(executable)], check=True)
            # Each fresh process has boot-equivalent static zero initialization.
            # -1 is success; 0..5 fault thread creation; 6..11 fault handoff.
            for scenario in range(-1, 12):
                result = subprocess.run([str(executable), str(scenario)],
                                        capture_output=True, text=True, timeout=10,
                                        preexec_fn=no_core)
                detect = mutation and (name == 'retry-live-engines' or scenario >= 0)
                if detect:
                    assert result.returncode != 0 and 'Assertion' in result.stderr, (name, scenario)
                else:
                    assert result.returncode == 0, (scenario, result.stderr)
            count = 12 if name == 'late-started-flag' else 13
            print(name + ': ' + ('DETECTED (%d scenarios)' % count if mutation else 'PASS (13 scenarios)'))


if __name__ == '__main__':
    main()
