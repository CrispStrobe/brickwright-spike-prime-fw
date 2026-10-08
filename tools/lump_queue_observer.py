# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Bounded read-only observations of our exact own-kernel DATA ring, not an ABI."""
import struct
import re
try:
    INTEGER_TYPES=(int,long)
except NameError:
    INTEGER_TYPES=(int,)
try:
    STRING_TYPES=(basestring,)
except NameError:
    STRING_TYPES=(str,)
FIELDS={'frames':576,'session':8,'dropped':4,'head':1,'tail':1,'count':1,'active':1}


def validate_layout(layout, digest, symbol):
    if not isinstance(layout,dict) or not isinstance(layout.get('fields'),dict):
        raise ValueError('Missing own-kernel queue layout')
    names=('address','stride','queueOffset','queueSize','portOffset','count')
    if any(type(layout.get(k)) not in INTEGER_TYPES for k in names):
        raise ValueError('Non-integer queue extent')
    base,stride=layout['address'],layout['stride']
    offset,size=layout['queueOffset'],layout['queueSize']
    fields=layout['fields']
    if (not isinstance(digest,STRING_TYPES) or not re.match(r'^[0-9a-f]{64}$',digest)
            or layout.get('schema')!=1 or layout.get('kernelSha256')!=digest
            or type(symbol) not in INTEGER_TYPES or base!=symbol or base%8
            or layout['count']!=6 or not 592<=stride<=8192
            or not 592<=size<=1024 or not 0<=offset<=stride-size or offset%8
            or not 0<=layout['portOffset']<stride or offset<=layout['portOffset']<offset+size
            or not 0x20000000<=base<base+6*stride<=0x20020000
            or set(fields)!=set(FIELDS)):
        raise ValueError('Queue layout does not match bounded own-kernel ELF')
    occupied=set()
    for name,width in FIELDS.items():
        at=fields[name]
        if type(at) not in INTEGER_TYPES or not 0<=at<=size-width:
            raise ValueError('Queue member outside its extent')
        region=set(range(at,at+width))
        if occupied.intersection(region):raise ValueError('Overlapping queue members')
        occupied.update(region)
    if fields['session']%8 or fields['dropped']%4:
        raise ValueError('Unaligned queue counters')
    return layout


class LumpQueueObserver(object):
    def __init__(self, layout, digest, symbol, read8, paused):
        self.layout=validate_layout(layout,digest,symbol)
        self.read8,self.paused=read8,paused
        engine=layout['address']+5*layout['stride']
        self.port_address=engine+layout['portOffset']
        self.base=engine+layout['queueOffset']

    def bytes(self,address,length):
        values=[int(self.read8(address+i)) for i in range(length)]
        if any(not 0<=v<=255 for v in values):raise ValueError('Non-byte queue observation')
        return b''.join(struct.pack('B',v) for v in values)

    def header(self):
        f=self.layout['fields']
        return dict(session=struct.unpack('<Q',self.bytes(self.base+f['session'],8))[0],
            dropped=struct.unpack('<I',self.bytes(self.base+f['dropped'],4))[0],
            **{name:int(self.read8(self.base+f[name])) for name in ('head','tail','count','active')})

    def snapshot(self):
        if not self.paused():raise ValueError('Queue observation requires paused emulation')
        if int(self.read8(self.port_address))!=5:raise ValueError('Own-kernel F engine mismatch')
        first=self.header()
        if not 0<=first['head']<16 or not 0<=first['tail']<16 or not 0<=first['count']<=16 or first['active'] not in (0,1):
            raise ValueError('Malformed queue observation')
        # A pause can land inside a multi-instruction ring update. Reject it,
        # rather than interpreting intermediate fields as an admission witness.
        if first['head']!=(first['tail']+first['count'])%16:return None
        if not first['active'] and (first['count'] or first['head'] or first['tail']):return None
        if first['active'] and not first['session']:return None
        frame=self.bytes(self.base+self.layout['fields']['frames']+36*first['tail'],36) if first['count'] else None
        if self.header()!=first or not self.paused():return None
        first['frame']=frame
        return first
