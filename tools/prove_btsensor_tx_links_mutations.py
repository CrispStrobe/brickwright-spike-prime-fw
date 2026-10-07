#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Require real host comparisons to reject two compiled TX regressions."""
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'apps/btsensor/btsensor_tx.c').read_text()
mutations = {
    'redirect-to-selected-link': ('brickwright_hub_transport_send(link, pending.data, pending.len)',
                                'brickwright_hub_transport_send(g_link, pending.data, pending.len)'),
    'retain-old-session-response': ('g_responses[i].tag.link == link) g_responses[i].tag.used = false;',
                                   'g_responses[i].tag.link == link) (void)0;'),
}


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


with tempfile.TemporaryDirectory(prefix='btsensor-tx-link-mutations-') as directory:
    build = Path(directory)
    for name, replacement in [('baseline', None), *mutations.items()]:
        text = source
        if replacement:
            before, after = replacement
            assert text.count(before) == 1, name + ': source boundary changed'
            text = text.replace(before, after)
        candidate = build / (name + '.c')
        candidate.write_text(text)
        executable = build / name
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-pthread',
            '-DCONFIG_APP_BTSENSOR_RING_DEPTH=4', '-I' + str(ROOT / 'apps/btsensor'),
            '-I' + str(ROOT / 'bluetooth/zephyr_compat/include'), str(candidate),
            str(ROOT / 'apps/btsensor/test/test_btsensor_tx_links.c'), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True, preexec_fn=no_core, timeout=10)
        if name == 'baseline':
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0 and 'Assertion' in result.stderr, name + ': comparison did not detect mutation'
        print(name + ': ' + ('PASS' if name == 'baseline' else 'DETECTED'))
