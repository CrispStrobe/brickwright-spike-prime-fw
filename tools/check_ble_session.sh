#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python3 - "$root" <<'PY'
from pathlib import Path
import os, subprocess, sys, tempfile
root = Path(sys.argv[1])
with tempfile.TemporaryDirectory(prefix='ble-session-', dir=os.environ.get('TMPDIR')) as folder:
    executable = Path(folder) / 'test'
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-I' + str(root / 'bluetooth/zephyr_compat/test/session_stubs'),
        '-I' + str(root / 'bluetooth/zephyr_compat/include'),
        str(root / 'bluetooth/zephyr_compat/test/test_ble_session.c'), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=10)
PY
