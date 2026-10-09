#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Validate feature discovery only in our own protected userspace ARM ELF."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess

SYMBOL = 'g_bw_program_addressed_sensor_abi'
FLASH_START, FLASH_END = 0x08060000, 0x08100000


def validate(raw, symbols):
    if (not 52 <= len(raw) <= 64 * 1024 * 1024
            or raw[:7] != b'\x7fELF\x01\x01\x01'
            or struct.unpack_from('<HHI', raw, 16) != (2, 40, 1)):
        raise ValueError('requires own little-endian ARM ELF32 executable')
    matches = [line.split() for line in symbols.splitlines()
               if line.split() and line.split()[-1] == SYMBOL]
    if len(matches) != 1 or len(matches[0]) != 4 or matches[0][2] not in ('R', 'T'):
        raise ValueError('requires exactly one global read-only feature symbol')
    address, size = (int(v, 16) for v in matches[0][:2])
    if size != 4 or address % 4 or not FLASH_START <= address <= FLASH_END - 4:
        raise ValueError('feature symbol must be an aligned four-byte userspace flash object')
    phoff = struct.unpack_from('<I', raw, 28)[0]
    ehsize, phsize, phcount = struct.unpack_from('<HHH', raw, 40)
    if (ehsize != 52 or phsize != 32 or not 1 <= phcount <= 128
            or phoff < 52 or phoff + phsize * phcount > len(raw)):
        raise ValueError('invalid program header extent')
    shoff = struct.unpack_from('<I', raw, 32)[0]
    shsize, shcount = struct.unpack_from('<HH', raw, 46)
    if (shsize != 40 or not 1 <= shcount <= 4096 or shoff < 52
            or shoff + shsize * shcount > len(raw)):
        raise ValueError('invalid section header extent')
    sections = [struct.unpack_from('<10I', raw, shoff + i * shsize) for i in range(shcount)]
    objects = []
    for section in sections:
        _, kind, _, _, offset, size, link, _, _, entrysize = section
        if kind != 2:
            continue
        if (entrysize != 16 or size % 16 or offset + size > len(raw)
                or not 0 <= link < shcount):
            raise ValueError('invalid symbol table')
        names = sections[link]
        namebase, namesize = names[4:6]
        if names[1] != 3 or namebase + namesize > len(raw):
            raise ValueError('invalid symbol names')
        for pos in range(offset, offset + size, 16):
            name, value, width, info, other, index = struct.unpack_from('<IIIBBH', raw, pos)
            if name >= namesize:
                raise ValueError('invalid symbol name offset')
            end = raw.find(b'\0', namebase + name, namebase + namesize)
            if end < 0:
                raise ValueError('unterminated symbol name')
            if raw[namebase + name:end] != SYMBOL.encode('ascii'):
                continue
            if info != 0x11 or value != address or width != 4 or not 0 < index < shcount:
                raise ValueError('requires global four-byte OBJECT symbol')
            target = sections[index]
            _, kind, flags, start, at, length, _, _, _, _ = target
            if (kind != 1 or not flags & 2 or flags & 1 or at + length > len(raw)
                    or not start <= address <= start + length - 4):
                raise ValueError('feature section must be allocated and nonwritable')
            objects.append(at + address - start)
    if len(objects) != 1:
        raise ValueError('requires exactly one feature OBJECT')
    object_offset = objects[0]
    covering = []
    for index in range(phcount):
        kind, offset, start, physical, files, memory, flags, align = struct.unpack_from(
            '<8I', raw, phoff + index * phsize)
        if kind != 1:
            continue
        if (files > memory or offset + files > len(raw)
                or start + memory > 0x100000000 or physical + memory > 0x100000000):
            raise ValueError('invalid load segment extent')
        if ((start < address + 4 and address < start + memory)
                or (physical < address + 4 and address < physical + memory)):
            covering.append((offset, start, physical, files, flags))
    if len(covering) != 1:
        raise ValueError('feature must belong to exactly one load segment')
    offset, start, physical, files, flags = covering[0]
    if (not flags & 4 or physical != start
            or not start <= address <= start + files - 4):
        raise ValueError('feature must be read-only, flash-loaded and file-backed')
    if offset + address - start != object_offset:
        raise ValueError('section and load mappings disagree')
    value = struct.unpack_from('<I', raw, object_offset)[0]
    if value != 1:
        raise ValueError('unsupported addressed sensor feature version')
    return {'abi': value, 'address': address, 'userspaceSha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--nm-tool', default='arm-none-eabi-nm')
    args = parser.parse_args()
    symbols = subprocess.check_output([args.nm_tool, '-S', '--defined-only', str(args.elf)], text=True)
    result = validate(args.elf.read_bytes(), symbols)
    print('addressed-sensor-marker: abi=%d address=0x%08x userspaceSha256=%s' %
          (result['abi'], result['address'], result['userspaceSha256']))


if __name__ == '__main__':
    main()
