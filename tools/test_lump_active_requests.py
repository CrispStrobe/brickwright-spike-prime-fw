#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic-host controls for the active fixture; never actual guest evidence."""
import struct
import io
from pathlib import Path
from types import ModuleType
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import lump_request_transport as api
BASE,OUT=0x20020000,0x20020020

class SyntheticWorker:
    def __init__(self, fault=None):
        self.words={BASE+i:0 for i in range(0,32,4)}
        self.queue=[];self.sequence=0;self.session=0;self.fault=fault
        self.writes=[];self.inputs=[];self.paused=True;self.complete=True
        self.port=SimpleNamespace(State='Detached',BridgeDrive=0,Timeouts=0,
            TransmittedFrames=0,DataReportsRemaining=0,SelectedMode=0)
        self.port.Attach=self.attach;self.port.Detach=self.detach
        self.port.SetDataReportBudget=self.budget
    def attach(self, name):
        self.inputs.append(('attach',name));self.queue=[]
        if self.fault!='reuse-identity' or not self.session:self.session+=1
        self.port.State='Streaming'
        self.port.Device=SimpleNamespace(TypeId=62,SetDistance=self.distance)
    def distance(self, value): self.value=value;self.inputs.append(('distance',value))
    def detach(self):
        self.inputs.append(('detach',));self.port.State='Detached'
        if self.fault!='retain-detached':self.queue=[]
    def budget(self, value):self.inputs.append(('budget',value));self.port.DataReportsRemaining=value
    def read(self,address):return self.words[address]
    def write(self,address,value):
        if address not in [BASE,BASE+4,BASE+8,BASE+12]:raise AssertionError('Unexpected guest write')
        self.writes.append((address,value));self.words[address]=value
    def advance(self,ms):
        if self.port.DataReportsRemaining:
            self.queue.append(api.ActiveSessionFixture.frame(self.value))
            self.port.DataReportsRemaining=0;self.port.TransmittedFrames+=1
        seq=self.words[BASE+8]
        if not self.complete or seq==self.words[BASE+16]:return
        op=self.words[BASE+12];records=[]
        if op==7:
            for i in range(5):records.append((-1,22 if i==0 else 14,b''))
            if self.fault=='consume-invalid' and self.queue:self.queue.pop(0)
        if self.queue:
            frame=self.queue[0]
            if self.fault!='duplicate-legacy' or op!=1:self.queue.pop(0)
            if op!=1:frame=struct.pack('<Q',self.session)+frame+b'\0'*4
            if self.fault=='corrupt-payload':frame=frame[:-1]+b'\xff'
            records.append((0,0,frame))
        else:records.append((-1,11,b'\xa5'*(36 if op==1 else 48)))
        self.sequence+=1
        words=[0x42575251,1,2,self.sequence,op,len(records),3,0,0,0]
        for result,error,data in records:
            words += [result&0xffffffff,error,len(data)]+list(struct.unpack('<12I',data+b'\0'*(48-len(data))))
        words += [0]*(100-len(words))
        self.words.update({OUT+i*4:v for i,v in enumerate(words)})
        self.words.update({BASE+16:seq,BASE+20:0,BASE+24:self.sequence,BASE+28:op})
    def fixture(self):
        return api.ActiveSessionFixture(BASE,OUT,self.read,self.write,lambda:self.paused,self.advance,self.port,lambda:0)

class Contract(unittest.TestCase):
    def test_exact_sequence_and_write_capability(self):
        w=SyntheticWorker();result=w.fixture().run()
        self.assertEqual(result,{'firstSession':1,'replacementSession':2,'requests':8,'externalReports':5})
        self.assertEqual(len(w.writes),32)
        self.assertEqual([v for a,v in w.writes if a==BASE+12],[7,0,1,0,0,0,0,0])
        self.assertEqual([v for a,v in w.writes if a==BASE+8],list(range(1,9)))
        self.assertEqual([item[1] for item in w.inputs if item[0]=='distance'],[1111,2222,3333,4444,5555])
    def test_broken_worker_behaviours_are_detected(self):
        for fault in ('consume-invalid','duplicate-legacy','reuse-identity','corrupt-payload'):
            with self.subTest(fault=fault),self.assertRaises(AssertionError):SyntheticWorker(fault).fixture().run()
    def test_detach_discards_old_frame(self):
        w=SyntheticWorker('retain-detached')
        with self.assertRaisesRegex(AssertionError,'empty'):w.fixture().run()
    def test_admission_before_any_input_or_guest_write(self):
        for kind in ('running','pending','overlap'):
            w=SyntheticWorker()
            if kind=='running':w.paused=False
            if kind=='pending':w.words[BASE+8]=1
            with self.subTest(kind=kind),self.assertRaises((ValueError,RuntimeError)):
                api.ActiveSessionFixture(BASE,BASE if kind=='overlap' else OUT,w.read,w.write,lambda:w.paused,w.advance,w.port)
            self.assertEqual(w.writes,[]);self.assertEqual(w.inputs,[])
    def test_no_fabricated_completion_on_guest_timeout(self):
        w=SyntheticWorker();w.complete=False
        with self.assertRaisesRegex(AssertionError,'Guest deadline'):w.fixture().run()
        self.assertEqual(w.words[BASE+8],1);self.assertEqual(w.words[BASE+16],0)
        self.assertEqual(len(w.writes),4)
    def test_host_deadline_is_cooperative(self):
        w=SyntheticWorker();f=w.fixture()
        f.clock=iter([0,121]).__next__
        with self.assertRaisesRegex(AssertionError,'Host deadline'):f.wait(lambda:False,10,'test')
        self.assertEqual(w.writes,[])
    def test_desynchronization_and_motor_drive_fail(self):
        for state,drive in [('Attached',0),('Streaming',1)]:
            w=SyntheticWorker();f=w.fixture();w.port.State=state;w.port.BridgeDrive=drive
            with self.assertRaises(AssertionError):f.emit(1111)
            self.assertEqual(w.inputs,[])
    def test_comparison_mutations_fail_controls(self):
        original=Path(api.__file__).read_text()
        mutations={
            'reuse-replacement-identity': [('if replaced<=first:', 'if False:')],
            'ignore-payload': [
                ("if data!=self.frame(distance):", "if False:"),
                ("if not session or data[8:]!=self.frame(distance)+b'\\x00'*4:", "if not session:")],
        }
        for name,replacements in mutations.items():
            source=original
            for old,new in replacements:
                self.assertEqual(source.count(old),1)
                source=source.replace(old,new)
            mutant=ModuleType('mutated_active_validator')
            exec(compile(source,name,'exec'),mutant.__dict__)
            with patch.dict(globals(),api=mutant):
                suite=unittest.TestSuite([Contract('test_broken_worker_behaviours_are_detected')])
                result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            self.assertEqual(len(result.errors),0, 'Setup failures are not mutation detection')
            self.assertGreaterEqual(len(result.failures),1,name+' escaped controls')

if __name__=='__main__':unittest.main()
