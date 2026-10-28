#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Stage the legacy paired-IMU/NOR fixture with the reviewed aggregate GSCLK.

The compiled Runtime must contain STM32TLCClock and TLC5955. Preserve the
source IMU/NOR fixture; replace only the display and its exact-rate clock.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def stage(runtime, output):
    if output.exists():
        raise ValueError('output exists; preserve prior evidence')
    inputs = {
        'stm32f4.repl': runtime / 'platforms/cpus/stm32f4.repl',
        'spike-prime.repl': ROOT / 'simulation/renode/spike-prime.repl',
        'spike-prime-custom-dma.repl': ROOT / 'simulation/renode/spike-prime-custom-dma.repl',
    }
    prepared, files = {}, {}
    for name, path in inputs.items():
        raw = path.read_bytes()
        source = '\n'.join(line for line in raw.decode().splitlines()
                           if 'ApplySVD @https://' not in line)+'\n'
        if name == 'stm32f4.repl':
            old = ('timer12: Timers.STM32_Timer @ sysbus 0x40001800\n'
                   '    -> nvic@43\n    frequency: 10000000\n    initialLimit: 0xFFFF')
            if source.count(old) != 1:
                raise ValueError('reviewed TIM12 declaration changed')
            source = source.replace(old, 'timer12: Timers.STM32TLCClock @ sysbus 0x40001800\n'
                                    '    frequency: 96000000\n    initialLimit: 0xFFFF\n    display: display')
            source, count = re.subn(r'^timer12:\n(?:    [^\n]*\n)+', '', source, flags=re.M)
            if count != 1:
                raise ValueError('reviewed TIM12 output wiring changed')
        elif name == 'spike-prime.repl':
            old = 'using "platforms/cpus/stm32f4.repl"'
            if source.count(old) != 1 or source.count('display: SPIKEPrime.TLC5955 @ spi1') != 1:
                raise ValueError('reviewed fixture changed')
            source = source.replace(old, 'using "./stm32f4.repl"')
            source = source.replace('display: SPIKEPrime.TLC5955 @ spi1', 'display: SPI.TLC5955 @ spi1')
        if 'http://' in source or 'https://' in source:
            raise ValueError('network-dependent topology')
        prepared[name] = source
        files[name] = {'sourceSha256': hashlib.sha256(raw).hexdigest(),
                       'stagedSha256': hashlib.sha256(source.encode()).hexdigest()}
    output.mkdir(parents=True)
    for name, source in prepared.items():
        (output / name).write_text(source)
    (output / 'topology-receipt.json').write_text(json.dumps({
        'scope': 'legacy paired-IMU/NOR fixture; compiled TLC5955 and exact 96 MHz aggregate TIM12',
        'files': files}, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    stage(a.runtime.resolve(), a.output.resolve())
