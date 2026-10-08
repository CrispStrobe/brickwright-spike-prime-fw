#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python3 - "$root" <<'PY'
import os, resource, subprocess, sys, tempfile
from pathlib import Path
root = Path(sys.argv[1])
def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
with tempfile.TemporaryDirectory(prefix='tx-drain-', dir=os.environ.get('TMPDIR')) as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-DCONFIG_APP_BTSENSOR_RING_DEPTH=4', '-I' + str(root / 'apps/btsensor'),
        '-I' + str(root / 'bluetooth/zephyr_compat/include'),
        str(root / 'apps/btsensor/test/test_btsensor_tx_drain.c'), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=10, preexec_fn=no_core)
PY
