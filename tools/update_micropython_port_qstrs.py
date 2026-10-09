#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Extend the retained MIT qstr table with four sorted port constants.

Preserve the original generated rows and static .mpy ABI pool. This does not
regenerate or reclassify the retained MicroPython sources or their licence.
"""
import argparse
import hashlib
from pathlib import Path
import re

BASE_SHA256='e350c7a036266ddbe678d202b82b44d632fbb10f250e7a3b19fc718a8b3fa911'
ROOT=Path(__file__).resolve().parents[1]

def extension():
    # One-byte qstr hashes for single ASCII letters, per retained configuration.
    return ''.join('QDEF1(MP_QSTR_%s, %d, 1, "%s")\n' % (c,((5381*33)^ord(c))&255,c) for c in 'CDEF')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');a=parser.parse_args()
    path=ROOT/'third_party/micropython-embed/genhdr/qstrdefs.generated.h'
    text=path.read_text();extra=extension();base=text.replace(extra,'')
    assert hashlib.sha256(base.encode()).hexdigest()==BASE_SHA256, 'Retained table changed; review its source before updating'
    marker='QDEF1(MP_QSTR_B, 231, 1, "B")\n';assert base.count(marker)==1
    expected=base.replace(marker,marker+extra)
    names=re.findall(r'^QDEF1\(MP_QSTR_[^,]+, \d+, \d+, "([^"\\]*)"\)',expected,re.M)
    assert names==sorted(names), 'Constant pool must remain sorted'
    if a.check:assert text==expected, 'Missing reviewed port qstr extension'
    else:path.write_text(expected)
    print('Port qstr extension verified; original rows/static pool preserved')

if __name__=='__main__':main()
