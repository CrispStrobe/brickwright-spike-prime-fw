#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Validate instruction ABI 2 discovery (ops 7/8) in our own protected userspace ARM ELF."""
import argparse
from pathlib import Path
import subprocess
from check_addressed_sensor_marker import validate as validate_marker

SYMBOL = 'g_bw_program_instruction_abi'
VERSION = 2


def validate(raw, symbols):
    return validate_marker(raw, symbols, SYMBOL, VERSION)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--nm-tool', default='arm-none-eabi-nm')
    args = parser.parse_args()
    symbols = subprocess.check_output([args.nm_tool, '-S', '--defined-only', str(args.elf)], text=True)
    result = validate(args.elf.read_bytes(), symbols)
    print('instruction-abi-marker: abi=%d address=0x%08x userspaceSha256=%s' %
          (result['abi'], result['address'], result['userspaceSha256']))


if __name__ == '__main__':
    main()
