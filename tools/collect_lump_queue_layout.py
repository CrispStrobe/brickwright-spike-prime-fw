#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Resolve bounded read-only queue offsets from our debug-enabled ARM kernel only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from collect_legoport_observation_layout import dies
from lump_queue_observer import validate_layout,FIELDS


def structures(lines):
    found={};active=None
    for die in dies(lines):
        if active is not None and die['depth']<=active['depth']:
            if active['size'] is not None:
                item=(int(active['size'],0),tuple(sorted((k,int(v,0)) for k,v in active['members'].items())))
                found.setdefault(active['name'],set()).add(item)
            active=None
        attrs=die['attributes']
        if die['tag']=='DW_TAG_structure_type' and attrs.get('name') in ('lump_engine_s','lump_data_queue_s'):
            active={'depth':die['depth'],'name':attrs['name'],'size':attrs.get('byte_size'),'members':{}}
        elif active is not None and die['depth']==active['depth']+1 and die['tag']=='DW_TAG_member':
            active['members'][attrs.get('name')]=attrs.get('data_member_location')
    if active is not None and active['size'] is not None:
        item=(int(active['size'],0),tuple(sorted((k,int(v,0)) for k,v in active['members'].items())))
        found.setdefault(active['name'],set()).add(item)
    if set(found)!=set(('lump_engine_s','lump_data_queue_s')) or any(len(v)!=1 for v in found.values()):
        raise ValueError('Missing or conflicting own-kernel queue types')
    return {k:(next(iter(v))[0],dict(next(iter(v))[1])) for k,v in found.items()}


def collect(kernel):
    raw=kernel.read_bytes()
    if len(raw)<20 or len(raw)>64*1024*1024 or raw[:6]!=b'\x7fELF\x01\x01' or struct.unpack_from('<H',raw,18)[0]!=40:
        raise ValueError('Requires our debug-enabled ARM ELF32 kernel')
    symbols=subprocess.check_output(['arm-none-eabi-nm','-S','--defined-only',str(kernel)],text=True)
    entries=re.findall(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+[bB]\s+g_lump$',symbols,re.M)
    if len(entries)!=1:raise ValueError('Expected one own-kernel LUMP array')
    with subprocess.Popen(['arm-none-eabi-readelf','--debug-dump=info',str(kernel)],stdout=subprocess.PIPE,text=True) as process:
        try:
            layouts=structures(process.stdout)
        except BaseException:
            process.kill()
            process.communicate()
            raise
        if process.wait()!=0:raise ValueError('Own-kernel debug metadata failed')
    stride,engine=layouts['lump_engine_s'];size,queue=layouts['lump_data_queue_s']
    base,length=(int(v,16) for v in entries[0])
    if length!=6*stride:raise ValueError('Own-kernel LUMP array extent mismatch')
    digest=hashlib.sha256(raw).hexdigest()
    layout={'schema':1,'scope':'read-only own-kernel F queue, not a guest ABI','kernelSha256':digest,
        'address':base,'stride':stride,'count':6,'queueOffset':engine['dq'],'queueSize':size,
        'portOffset':engine['port'],'fields':{k:queue[k] for k in FIELDS}}
    return validate_layout(layout,digest,base)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    layout=collect(args.kernel.resolve())
    with args.output.open('x') as output:json.dump(layout,output,indent=2);output.write('\n')
    print('Own-kernel read-only F queue layout verified')
