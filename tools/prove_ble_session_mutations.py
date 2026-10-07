#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Require compiled comparisons to detect stale admission and lease regressions."""
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / 'bluetooth/zephyr_compat'


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run(source, test, name, includes):
    executable = source.parent / name
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-DCONFIG_APP_BTSENSOR_RING_DEPTH=4', *['-I' + str(p) for p in includes],
        *([str(source)] if test.name == 'test_btsensor_tx_links.c' else []),
        str(test), '-o', str(executable)], check=True)
    result = subprocess.run([str(executable)], capture_output=True, text=True,
                            timeout=10, preexec_fn=no_core)
    if name == 'baseline':
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0 and 'Assertion' in result.stderr, name + ': mutation not detected'
    print(name + ': ' + ('PASS' if name == 'baseline' else 'DETECTED'))


with tempfile.TemporaryDirectory(prefix='ble-session-mutations-') as directory:
    folder = Path(directory)
    (folder / 'src').mkdir()
    (folder / 'test').mkdir()
    test = folder / 'test/test_ble_session.c'
    test.write_bytes((COMPAT / 'test/test_ble_session.c').read_bytes())
    original = (COMPAT / 'src/hub_transport.c').read_text()
    mutations = {
        'ignore-connection-identity': ('!le_connection || le_identity != identity', '!le_connection'),
        'omit-final-connection-lease': ('struct bt_conn *connection = bt_conn_ref(le_connection);',
                                      'struct bt_conn *connection = le_connection;'),
    }
    source = folder / 'src/hub_transport.c'
    for name, replacement in [('baseline', None), *mutations.items()]:
        candidate = original
        if replacement:
            before, after = replacement
            assert candidate.count(before) == 1
            candidate = candidate.replace(before, after)
        source.write_text(candidate)
        run(source, test, name, [COMPAT / 'test/session_stubs', COMPAT / 'include'])
    source = folder / 'tx.c'
    original = (ROOT / 'apps/btsensor/btsensor_tx.c').read_text()
    before = 'brickwright_hub_transport_send_ble(pending.tag.ble_identity, pending.data, pending.len)'
    after = '(brickwright_hub_transport_capture_ble(&pending.tag.ble_identity), ' + before + ')'
    assert original.count(before) == 1
    for name, candidate in [('baseline', original), ('recapture-at-send', original.replace(before, after))]:
        source.write_text(candidate)
        run(source, ROOT / 'apps/btsensor/test/test_btsensor_tx_links.c', name,
            [ROOT / 'apps/btsensor', COMPAT / 'include'])
