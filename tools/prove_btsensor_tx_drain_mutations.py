#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Require real compiled assertions to reject drain-identity regressions."""
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
original = (ROOT / 'apps/btsensor/btsensor_tx.c').read_text()
mutations = {
    'stale-expiry-clears-replacement':
        ('registration && g_drain_id == registration && g_timer_id == registration',
         'registration && g_drain_id && g_timer_id'),
    'stale-cancel-clears-replacement':
        ('bool canceled = registration && g_drain_id == registration;',
         'bool canceled = registration && g_drain_id;'),
    'overlapping-backend-operations':
        ('if (g_timer_pumping) { pthread_mutex_unlock(&g_lock); return; }',
         'if (false) { pthread_mutex_unlock(&g_lock); return; }'),
    'reuse-identity-after-init':
        ('g_selected = g_pumping = false;', 'g_selected = g_pumping = false; g_drain_counter = 0;'),
    'old-start-failure-clears-replacement':
        ('if (g_drain_id == id)', 'if (g_drain_id)'),
}

def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

with tempfile.TemporaryDirectory(prefix='tx-drain-mutations-') as directory:
    folder = Path(directory)
    (folder / 'test').mkdir()
    test = folder / 'test/test_btsensor_tx_drain.c'
    test.write_bytes((ROOT / 'apps/btsensor/test/test_btsensor_tx_drain.c').read_bytes())
    source = folder / 'btsensor_tx.c'
    for name, replacement in [('baseline', None), *mutations.items()]:
        candidate = original
        if replacement:
            before, after = replacement
            assert candidate.count(before) == 1, name
            candidate = candidate.replace(before, after)
        source.write_text(candidate)
        executable = folder / name
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-pthread',
            '-DCONFIG_APP_BTSENSOR_RING_DEPTH=4', '-I' + str(ROOT / 'apps/btsensor'),
            '-I' + str(ROOT / 'bluetooth/zephyr_compat/include'), str(test),
            '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True,
                                timeout=10, preexec_fn=no_core)
        if replacement:
            assert result.returncode != 0 and 'Assertion' in result.stderr, name + ': undetected'
        else:
            assert result.returncode == 0, result.stderr
        print(name + ': ' + ('DETECTED' if replacement else 'PASS'))
