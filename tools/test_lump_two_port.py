#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Two-port host adversaries; no kernel, UART or emulator is executed."""
import io
import struct
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import lump_two_port as pair
from test_lump_active_requests import SyntheticWorker,BASE,OUT


class DualWorker:
    def __init__(self, fault=None):
        self.workers={name:SyntheticWorker() for name in ('E','F')}
        self.words={BASE+i:0 for i in range(0,32,4)}
        self.writes=[];self.fault=fault
        for w in self.workers.values():w.complete=False
        if fault=='invalidate-other':
            original=self.workers['E'].port.Detach
            def detach():
                original();self.workers['F'].queue=[]
            self.workers['E'].port.Detach=detach
        if fault=='reuse-replacement':self.workers['E'].fault='reuse-identity'
    def read(self, address):return self.words[address]
    def write(self, address, value):
        if address not in (BASE,BASE+4,BASE+8,BASE+12):raise AssertionError('Unexpected guest write')
        self.words[address]=value;self.writes.append((address,value))
    def advance(self,ms):
        for w in self.workers.values():w.advance(ms)
        seq=self.words[BASE+8]
        if seq==self.words[BASE+16]:return
        op=self.words[BASE+12];name='E' if op>=8 else 'F'
        selected=self.workers[name]
        if self.fault=='swapped-replies':selected=self.workers['F' if name=='E' else 'E']
        selected.words.update({BASE+8:seq,BASE+12:(7 if op==9 else 0) if op>=8 else op})
        selected.complete=True;selected.advance(ms);selected.complete=False
        for address,value in selected.words.items():
            if address>=OUT:self.words[address]=value
        self.words.update({OUT+16:op,BASE+16:seq,BASE+20:0,BASE+24:selected.sequence,BASE+28:op})
        if self.fault=='cross-consumption':
            other=self.workers['F' if name=='E' else 'E']
            if other.queue:other.queue.pop(0)
    def fixture(self):
        return pair.TwoPortFixture(BASE,OUT,self.read,self.write,lambda:True,self.advance,
            {name:w.port for name,w in self.workers.items()},
            {name:w.observe for name,w in self.workers.items()},lambda:0)


class Contract(unittest.TestCase):
    def test_interleaving_and_equal_cross_port_identities(self):
        w=DualWorker();result=w.fixture().run()
        self.assertEqual(result,{'ports':['E','F'],'requests':12,'externalReports':9,
            'firstE':1,'replacementE':2,'stableF':1,'detachWaitMs':0})
        self.assertEqual([v for a,v in w.writes if a==BASE+12],[0,8,8,0,9,8,8,0,8,0,8,0])
        self.assertEqual([v for a,v in w.writes if a==BASE+8],list(range(1,13)))
        self.assertEqual(len(w.writes),48)
    def test_cross_port_faults(self):
        for fault in ('swapped-replies','cross-consumption','invalidate-other','reuse-replacement'):
            with self.subTest(fault=fault),self.assertRaises(AssertionError):DualWorker(fault).fixture().run()
    def test_pending_payload_and_identity_are_observed(self):
        for field,value in [('frame',b'bad'),('session',99),('active',False),('count',0),('dropped',1)]:
            w=DualWorker();f=w.fixture();e=f.fixtures['E'];e.attach();e.emit(123)
            original=e.observe
            def corrupt():
                state=original();state[field]=value;return state
            e.observe=corrupt
            with self.subTest(field=field),self.assertRaisesRegex(AssertionError,'unchanged pending'):
                f.pending('E',123,1)
    def test_failure_identifies_expected_frame_and_actual_queue(self):
        w=DualWorker();f=w.fixture();e=f.fixtures['E'];e.attach();e.emit(123)
        with self.assertRaisesRegex(AssertionError,'distance=456 session=1.*queue=.*modelState=Streaming'):
            f.pending('E',456,1)

    def test_sampling_failure_does_not_mask_original_deadline(self):
        w=DualWorker();f=w.fixture();e=f.fixtures['E'];e.attach();e.emit(123)
        original=e.observe;calls=[0]
        def observe():
            calls[0]+=1
            if calls[0]>21:raise ValueError('secondary sampling fault')
            return original()
        e.observe=observe
        with self.assertRaisesRegex(AssertionError,'Guest deadline:.*checkpoint=after-detach.*secondary sampling fault'):
            f.pending('E',456,1,'after-detach')

    def test_distinct_ports_and_observers_required(self):
        w=DualWorker();p=w.workers['E'].port;o=w.workers['E'].observe
        with self.assertRaises(ValueError):pair.TwoPortFixture(BASE,OUT,w.read,w.write,lambda:True,w.advance,
            {'E':p,'F':p},{'E':o,'F':o})
        self.assertEqual(w.writes,[])
    def test_comparison_mutants_are_assertion_detected(self):
        source=Path(pair.__file__).read_text()
        variants={
            'ignore-other-payload':("state['frame']==f.frame(distance)", 'True'),
            'ignore-other-identity':("state['session']==session", 'True'),
            'ignore-replacement-progression':('if replacement<=se:', 'if False:'),
        }
        for name,(old,new) in variants.items():
            self.assertEqual(source.count(old),1)
            mutant=ModuleType(name);exec(compile(source.replace(old,new),name,'exec'),mutant.__dict__)
            suite=unittest.TestSuite([Contract('test_pending_payload_and_identity_are_observed'),Contract('test_cross_port_faults')])
            with patch.dict(globals(),pair=mutant):result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            self.assertEqual(result.errors,[],name+' setup failure does not count')
            self.assertTrue(result.failures,name+' escaped assertions')

if __name__=='__main__':unittest.main()
