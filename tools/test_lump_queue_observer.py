#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Own-ELF metadata and read-only queue controls with synthetic bytes/DWARF."""
import copy
import io
import struct
import unittest
from lump_queue_observer import LumpQueueObserver,validate_layout
from collect_lump_queue_layout import structures
DIGEST='a'*64
BASE=0x20000000

def layout():
    return {'schema':1,'kernelSha256':DIGEST,'address':BASE,'stride':640,'count':6,
        'queueOffset':32,'queueSize':592,'portOffset':0,
        'fields':{'frames':0,'session':576,'dropped':584,'head':588,'tail':589,'count':590,'active':591}}

class Observer(unittest.TestCase):
    def setUp(self):
        self.l=layout();self.ram={BASE+i:0 for i in range(3840)}
        self.ram[BASE+3200]=5;self.q=BASE+3200+32;self.paused=True;self.reads=[]
        self.o=LumpQueueObserver(self.l,DIGEST,BASE,self.read,lambda:self.paused)
    def read(self,address):self.reads.append(address);return self.ram[address]
    def put(self,offset,data):self.ram.update({self.q+offset+i:v for i,v in enumerate(data)})
    def queued(self):
        self.put(576,struct.pack('<Q',7));self.put(588,b'\x01\x00\x01\x01')
        self.put(0,b'\x00\x02\0\0\x57\x04'+b'\0'*30)
    def test_positive_admission_and_read_extent(self):
        self.queued();s=self.o.snapshot()
        self.assertEqual((s['active'],s['count'],s['session']), (1,1,7))
        self.assertEqual(s['frame'],b'\x00\x02\0\0\x57\x04'+b'\0'*30)
        self.assertTrue(all(a==BASE+3200 or self.q<=a<self.q+592 for a in self.reads))
        self.assertFalse(hasattr(self.o,'write'))
    def test_idle_requires_completed_invalidation(self):
        self.assertEqual(self.o.snapshot()['count'],0)
        self.queued();self.ram[self.q+591]=0
        self.assertIsNone(self.o.snapshot())
        self.put(588,b'\0'*4)
        self.assertEqual(self.o.snapshot()['active'],0)
    def test_partial_ring_updates_are_not_admission(self):
        self.queued();self.ram[self.q+590]=0
        self.assertIsNone(self.o.snapshot())
        self.put(588,b'\x00\x00\x01\x01')
        self.assertIsNone(self.o.snapshot())
    def test_changed_header_is_not_admission(self):
        self.queued()
        def changing(address):
            value=self.read(address)
            if address==self.q+35:self.ram[self.q+584]=1
            return value
        self.o.read8=changing
        self.assertIsNone(self.o.snapshot())
    def test_running_or_wrong_engine_refused(self):
        self.paused=False
        with self.assertRaises(ValueError):self.o.snapshot()
        self.assertEqual(self.reads,[])
        self.paused=True;self.ram[BASE+3200]=4
        with self.assertRaises(ValueError):self.o.snapshot()
    def test_digest_symbol_bounds_and_alias_refused_before_reads(self):
        bad=[]
        for key,value in [('address',0x20020000),('stride',True),('queueOffset',1),('queueSize',575),('portOffset',32),('count',5)]:
            x=layout();x[key]=value;bad.append(x)
        x=layout();x['fields']['count']=x['fields']['head'];bad.append(x)
        x=layout();x['fields']['session']=577;bad.append(x)
        for x in bad:
            with self.subTest(layout=x),self.assertRaises(ValueError):LumpQueueObserver(x,DIGEST,BASE,self.read,lambda:True)
        for digest,symbol in [('b'*64,BASE),(DIGEST,BASE+8),('bad','bad')]:
            with self.assertRaises(ValueError):validate_layout(layout(),digest,symbol)
        self.assertEqual(self.reads,[])
    def test_invalid_counts_refused(self):
        for offset,value in [(588,16),(589,16),(590,17),(591,2)]:
            self.queued();self.ram[self.q+offset]=value
            with self.assertRaises(ValueError):self.o.snapshot()

class DebugMetadata(unittest.TestCase):
    def debug(self,name,size,fields):
        text=' <1><1>: Abbrev Number: 1 (DW_TAG_structure_type)\n DW_AT_name : '+name+'\n DW_AT_byte_size : '+str(size)+'\n'
        for i,(key,offset) in enumerate(fields.items()):
            text+=' <2><%x>: Abbrev Number: 2 (DW_TAG_member)\n DW_AT_name : %s\n DW_AT_data_member_location : %d\n'%(i+2,key,offset)
        return text
    def test_exact_types_and_identical_definitions(self):
        q=self.debug('lump_data_queue_s',592,layout()['fields'])
        e=self.debug('lump_engine_s',640,{'port':0,'dq':32})
        result=structures(io.StringIO(q+e+q))
        self.assertEqual(result['lump_engine_s'],(640,{'port':0,'dq':32}))
        self.assertEqual(result['lump_data_queue_s'],(592,layout()['fields']))
    def test_missing_and_conflicting_types_refused(self):
        q=self.debug('lump_data_queue_s',592,layout()['fields'])
        e=self.debug('lump_engine_s',640,{'port':0,'dq':32})
        for text in (q,q+e+self.debug('lump_engine_s',648,{'port':0,'dq':32})):
            with self.assertRaises(ValueError):structures(io.StringIO(text))

if __name__=='__main__':unittest.main()
