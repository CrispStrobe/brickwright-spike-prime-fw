#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Reuse the reviewed Runtime's public board topology with compiled models.

The same aggregate display-clock policy is used by Runtime's staging tool.
No C# type is compiled a second time, no model algorithm is copied, no firmware
is loaded or downloaded, and source notices in every platform are preserved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

FILES = ('boards/spike-prime.repl', 'boards/spike-prime-brick-devices.repl',
         'cpus/stm32f413vg.repl', 'cpus/stm32f4.repl')


def stage(runtime, output):
    if output.exists():
        raise ValueError('output exists; preserve earlier evidence')
    prepared, receipt = {}, {}
    for name in FILES:
        raw = (runtime / 'platforms' / name).read_bytes()
        source = raw.decode('utf8')
        source = '\n'.join(line for line in source.splitlines()
                           if 'ApplySVD @https://' not in line) + '\n'
        if name == 'cpus/stm32f4.repl':
            old = 'timer12: Timers.STM32_Timer'
            if source.count(old) != 1:
                raise ValueError('reviewed TIM12 topology changed')
            source = source.replace(old, 'timer12: Timers.STM32TLCClock')
            source = source.replace('    -> nvic@43\n', '')
            source = re.sub(r'^timer12:\n(?:    [^\n]*\n)+', '', source, flags=re.M)
        if name == 'boards/spike-prime-brick-devices.repl':
            old = 'timer12:\n    1 -> display@1'
            if source.count(old) != 1:
                raise ValueError('reviewed display-clock wiring changed')
            source = source.replace(old, 'timer12:\n    display: display')
        if 'https://' in source or 'http://' in source:
            raise ValueError('network-dependent platform cannot be staged')
        prepared[name] = source
        receipt[name] = {'sourceSha256': hashlib.sha256(raw).hexdigest(),
                         'stagedSha256': hashlib.sha256(source.encode()).hexdigest()}
    for name, source in prepared.items():
        path = output / 'platforms' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    (output / 'topology-receipt.json').write_text(json.dumps({
        'scope': 'public platform files; Runtime compiled models; aggregate TIM12 display clock',
        'files': receipt}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stage(args.runtime.resolve(), args.output.resolve())
