#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Locate read-only DCM observations in our own debug-enabled kernel ELF.

This diagnostic layout is tied to the exact kernel hash, not a supported guest
ABI. Never use it with reference/third-party firmware. Output stays private.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


def dies(lines):
    current = None
    for line in lines:
        match = re.match(r'\s*<(\d+)><[0-9a-f]+>: Abbrev Number: \d+(?: \(([^)]+)\))?', line)
        if match:
            if current is not None:
                yield current
            current = {'depth': int(match[1]), 'tag': match[2], 'attributes': {}}
        elif current is not None:
            match = re.search(r'DW_AT_(\w+)\s*:\s*(.*)', line)
            if match:
                current['attributes'][match[1]] = match[2].split(': ')[-1].strip()
    if current is not None:
        yield current


def collect(kernel):
    raw = kernel.read_bytes()
    if len(raw) < 20 or len(raw) > 64 * 1024 * 1024 or raw[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', raw, 18)[0] != 40:
        raise ValueError('requires our debug-enabled ARM ELF32 kernel')
    symbols = subprocess.check_output(['arm-none-eabi-nm', '-S', '--defined-only', str(kernel)], text=True)
    entries = re.findall(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+\w\s+g_legoport_state$', symbols, re.M)
    if len(entries) != 1:
        raise ValueError('expected one own-kernel DCM state array')
    layouts, active = [], None
    with subprocess.Popen(['arm-none-eabi-readelf', '--debug-dump=info', str(kernel)],
                          stdout=subprocess.PIPE, text=True) as process:
        for die in dies(process.stdout):
            if active is not None and die['depth'] <= active['depth']:
                layouts.append(active)
                active = None
            attrs = die['attributes']
            if die['tag'] == 'DW_TAG_structure_type' and attrs.get('name') == 'legoport_state_s':
                active = {'depth': die['depth'], 'size': attrs.get('byte_size'), 'members': {}}
            elif active is not None and die['depth'] == active['depth'] + 1 and die['tag'] == 'DW_TAG_member':
                active['members'][attrs.get('name')] = attrs.get('data_member_location')
        if process.wait() != 0:
            raise ValueError('kernel debug metadata could not be read')
    if active is not None:
        layouts.append(active)
    if len(layouts) != 1:
        raise ValueError('expected one complete DCM structure definition')
    layout = layouts[0]
    stride = int(layout['size'], 0)
    address, size = (int(value, 16) for value in entries[0])
    offsets = {key: int(layout['members'][key], 0) for key in ('confirmed_type', 'flags', 'event_counter')}
    if not (16 <= stride <= 512 and size == stride * 6 and 0x20000000 <= address < address + size <= 0x20010000
            and all(0 <= value < stride for value in offsets.values())
            and offsets['event_counter'] % 4 == 0 and offsets['event_counter'] + 4 <= stride):
        raise ValueError('DCM layout exceeds expected own-kernel memory bounds')
    return {'schema': 1, 'scope': 'read-only own-kernel diagnostic, not a stable ABI',
            'kernelSha256': hashlib.sha256(raw).hexdigest(), 'address': address,
            'stride': stride, 'count': 6, 'offsets': offsets}


def load_layout(path, kernel):
    layout = json.loads(path.read_text())
    if not isinstance(layout, dict) or not isinstance(layout.get('offsets'), dict):
        raise ValueError('observation layout must contain a bounded offsets object')
    offsets = layout['offsets']
    address, stride = layout.get('address', 0), layout.get('stride', 0)
    if not (layout.get('schema') == 1 and layout.get('count') == 6
            and layout.get('kernelSha256') == hashlib.sha256(kernel.read_bytes()).hexdigest()
            and type(address) is int and type(stride) is int and 16 <= stride <= 512
            and 0x20000000 <= address < address + 6 * stride <= 0x20010000
            and set(offsets) == {'confirmed_type', 'flags', 'event_counter'}
            and all(type(value) is int and 0 <= value < stride for value in offsets.values())
            and offsets['event_counter'] % 4 == 0 and offsets['event_counter'] + 4 <= stride):
        raise ValueError('observation layout does not match this own kernel or its bounded memory')
    return layout


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    layout = collect(args.kernel.resolve())
    with args.output.open('x') as out:
        json.dump(layout, out, indent=2)
        out.write('\n')
    print('Own-kernel read-only DCM layout verified')
