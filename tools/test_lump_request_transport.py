#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Read/write capability and correlation controls; not actual guest execution."""
import unittest
import io
from contextlib import redirect_stdout
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import lump_request_transport as transport
from lump_request_transport import submit,reply,publication,MAX_SEQUENCE
BASE=0x20020000
OUT=BASE+32
class Contract(unittest.TestCase):
    def setUp(self):
        self.words={BASE+i:0 for i in range(0,32,4)};self.writes=[]
    def read(self,address): return self.words[address]
    def write(self,address,value):
        self.assertIn(address,[BASE,BASE+4,BASE+8,BASE+12])
        self.writes.append((address,value));self.words[address]=value
    def test_only_request_words_and_sequence_last(self):
        self.assertEqual(submit(BASE,7,self.read,self.write,True),1)
        self.assertEqual(self.writes,[(BASE,0x42574c52),(BASE+4,1),(BASE+12,7),(BASE+8,1)])
        with self.assertRaises(RuntimeError): submit(BASE,0,self.read,self.write,True)
        self.assertEqual(len(self.writes),4)
    def test_rejected_requests_never_write(self):
        for base,op,paused in [(0,0,True),(BASE+1,0,True),(0x20040000-28,0,True),(True,0,True),(BASE,-1,True),(BASE,8,True),(BASE,True,True),(BASE,0,False)]:
            with self.subTest(base=base,op=op,paused=paused),self.assertRaises(ValueError): submit(base,op,self.read,self.write,paused)
        self.words[BASE+8]=self.words[BASE+16]=MAX_SEQUENCE
        with self.assertRaises(OverflowError): submit(BASE,0,self.read,self.write,True)
        self.assertEqual(self.writes,[])
    def test_reply_correlation_and_errors(self):
        self.assertIsNone(reply(BASE,1,0,self.read))
        self.words.update({BASE+8:1,BASE+16:1,BASE+20:0,BASE+24:4,BASE+28:0})
        self.assertEqual(reply(BASE,1,0,self.read)['publication'],4)
        with self.assertRaises(ValueError): reply(BASE,1,1,self.read)
        with self.assertRaises(ValueError): reply(BASE,0,0,self.read)
        self.words[BASE+24]=0
        with self.assertRaises(ValueError): reply(BASE,1,0,self.read)
        self.words[BASE+20]=0xffffffff-15
        self.assertEqual(reply(BASE,1,0,self.read)['result'],-16)
        self.words[BASE+16]=2
        with self.assertRaises(ValueError): reply(BASE,1,0,self.read)
        self.words[BASE+16]=1;self.words[BASE+8]=2
        with self.assertRaises(ValueError): reply(BASE,1,0,self.read)
    def test_changed_reply_is_rejected(self):
        self.words.update({BASE+8:1,BASE+16:1,BASE+20:0,BASE+24:4,BASE+28:0})
        reads=[0]
        def changing(address):
            if address==BASE+16:
                reads[0]+=1;return reads[0]
            return self.read(address)
        with self.assertRaises(ValueError): reply(BASE,1,0,changing)
    def output(self):
        words=[0x42575251,1,2,4,0,1,3,0,0,0]+[0xffffffff,11,48]+[0xa5a5a5a5]*12+[0]*75
        self.words.update({OUT+4*i:v for i,v in enumerate(words)})
    def test_publication_bytes_and_replacement(self):
        self.output()
        p=publication(OUT,4,0,self.read)
        self.assertEqual(p['records'],[{'result':-1,'errno':11,'data':b'\xa5'*48}])
        for sequence,selector in [(3,0),(4,1),(0,0)]:
            with self.assertRaises(ValueError): publication(OUT,sequence,selector,self.read)
        self.words[OUT+4*12]=49
        with self.assertRaises(ValueError): publication(OUT,4,0,self.read)
        self.words[OUT+4*12]=36
        with self.assertRaises(ValueError): publication(OUT,4,0,self.read)
    def test_changed_publication_refuses(self):
        self.output();calls=[0]
        def changing(address):
            if address==OUT+12:
                calls[0]+=1;return 4 if calls[0]<3 else 5
            return self.read(address)
        with self.assertRaises(ValueError): publication(OUT,4,0,changing)
class Bridge(unittest.TestCase):
    """Synthetic host worker only; the real worker remains an actual-guest gate."""
    def setUp(self):
        self.words={BASE+i:0 for i in range(0,32,4)}
        self.writes=[];self.advances=[];self.complete=True;self.corrupt=False
        self.machine=SimpleNamespace(IsPaused=True)
        def read(address): return self.words[address]
        def write(address,value):
            self.assertIn(address,[BASE,BASE+4,BASE+8,BASE+12])
            self.writes.append((address,value));self.words[address]=value
        self.machine.SystemBus=SimpleNamespace(ReadDoubleWord=read,WriteDoubleWord=write)
        def run(milliseconds):
            self.advances.append(milliseconds)
            if not self.complete or milliseconds==20:return
            sequence=self.words[BASE+8];selector=self.words[BASE+12]
            words=[0x42575251,1,2,sequence+1,selector,6 if selector==7 else 1,3,0,0,0]
            if selector==7:
                for i in range(5): words += [0xffffffff,22 if i==0 else 14,0]+[0]*12
            size=36 if selector==1 else 48
            words += [0xffffffff,14 if self.corrupt else 11,size]+[0xa5a5a5a5]*(size//4)+[0]*((48-size)//4)
            words += [0]*(100-len(words))
            self.words.update({OUT+4*i:v for i,v in enumerate(words)})
            self.words.update({BASE+16:sequence,BASE+20:0,BASE+24:sequence+1,BASE+28:selector})
        self.run=run
        self.modules={}
        for name,members in {
            'Antmicro.Renode.Core':{'EmulationManager':SimpleNamespace(Instance=SimpleNamespace(CurrentEmulation=SimpleNamespace(RunFor=run)))},
            'Antmicro.Renode.Time':{'TimeInterval':SimpleNamespace(FromMilliseconds=int)},
            'System':{'UInt64':int,'UInt32':int},
        }.items():
            self.modules[name]=ModuleType(name);self.modules[name].__dict__.update(members)
    def check(self,output=OUT,times=None):
        clock={'return_value':0} if times is None else {'side_effect':times}
        with patch.dict('sys.modules',self.modules), patch.object(transport,'monitor',SimpleNamespace(Machine=self.machine),create=True), patch.object(transport.time,'time',**clock),redirect_stdout(io.StringIO()) as text:
            transport.mc_check_lump_mailbox(hex(BASE),hex(output))
            return text.getvalue()
    def test_exact_correlated_roundtrips_and_scheduling(self):
        text=self.check()
        self.assertEqual(self.advances,[20,10,10,10])
        self.assertEqual(len(self.writes),12)
        for selector,sequence in [(7,1),(0,2),(1,3)]:
            self.assertIn('selector=%d sequence=%d publication=%d'%(selector,sequence,sequence+1),text)
    def test_admission_and_paused_interval_refusals(self):
        self.machine.IsPaused=False
        with self.assertRaises(ValueError):self.check()
        self.machine.IsPaused=True
        with self.assertRaises(ValueError):self.check(BASE)
        self.assertEqual(self.writes,[])
        def unpause(ms):self.machine.IsPaused=False
        self.modules['Antmicro.Renode.Core'].EmulationManager.Instance.CurrentEmulation.RunFor=unpause
        with self.assertRaisesRegex(AssertionError,'pause'):self.check()
        self.assertEqual(self.writes,[])
    def test_cooperative_deadlines_preserve_outstanding_request(self):
        self.complete=False
        with self.assertRaisesRegex(AssertionError,'one guest second'):self.check()
        self.assertEqual(self.words[BASE+8],1);self.assertEqual(self.words[BASE+16],0)
        self.assertEqual(len(self.writes),4)
        self.setUp();self.complete=False
        with self.assertRaisesRegex(AssertionError,'30 host seconds'):self.check(times=[0,31])
        self.assertEqual(self.words[BASE+8],1);self.assertEqual(self.words[BASE+16],0)
        self.assertEqual(self.advances,[20])
    def test_incorrect_actual_results_are_not_passes(self):
        self.corrupt=True
        with self.assertRaisesRegex(AssertionError,'calls failed'):self.check()
        self.assertEqual(self.words[BASE+16],1)
if __name__=='__main__': unittest.main()
