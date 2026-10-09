# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Declared simulation diagnostic request transport; never write result words."""
import struct
import time
MAX_SEQUENCE = 0xffffffff
MAGIC = 0x42574c52
try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)

def extent(base, size):
    if type(base) not in INTEGER_TYPES or base % 4 or not 0x20020000 <= base <= 0x20040000-size:
        raise ValueError('Diagnostic ELF extent is outside userspace static RAM')
    return base

def unsigned(value):
    value = int(value)
    if not 0 <= value <= MAX_SEQUENCE: raise ValueError('Non-word transport input')
    return value

def signed(value): return value if value < 0x80000000 else value-0x100000000

def submit(base, selector, read32, write32, paused):
    extent(base, 32)
    if not paused: raise ValueError('Diagnostic requests require paused emulation')
    if type(selector) not in INTEGER_TYPES or not 0 <= selector < 10: raise ValueError('Unknown fixed operation')
    current = unsigned(read32(base+8)); acknowledged = unsigned(read32(base+16))
    if current != acknowledged: raise RuntimeError('A diagnostic request is outstanding')
    if current == MAX_SEQUENCE: raise OverflowError('Diagnostic sequence exhausted; reboot required')
    sequence = current+1
    # Commit last; only these four request words may be written.
    for offset,value in [(0,MAGIC),(4,1),(12,selector),(8,sequence)]: write32(base+offset,value)
    return sequence

def reply(base, sequence, selector, read32):
    extent(base,32)
    if type(sequence) not in INTEGER_TYPES or not 1 <= sequence <= MAX_SEQUENCE: raise ValueError('Bad expected sequence')
    if type(selector) not in INTEGER_TYPES or not 0 <= selector < 10: raise ValueError('Bad expected operation')
    current=unsigned(read32(base+8))
    if current < sequence: return None
    if current > sequence: raise ValueError('Diagnostic request was replaced')
    before=unsigned(read32(base+16))
    if before < sequence: return None
    if before > sequence: raise ValueError('Diagnostic reply was replaced')
    result=signed(unsigned(read32(base+20)))
    publication=unsigned(read32(base+24)); actual=unsigned(read32(base+28))
    if unsigned(read32(base+16)) != before or unsigned(read32(base+8)) != current: raise ValueError('Diagnostic reply changed')
    if actual != selector: raise ValueError('Diagnostic reply operation mismatch')
    if result == 0 and not publication: raise ValueError('Missing guest publication')
    return {'sequence':before,'result':result,'publication':publication,'selector':actual}

def publication(base, sequence, selector, read32):
    extent(base,400)
    if type(sequence) not in INTEGER_TYPES or not 1 <= sequence <= MAX_SEQUENCE: raise ValueError('Bad publication sequence')
    if type(selector) not in INTEGER_TYPES or not 0 <= selector < 10: raise ValueError('Bad publication operation')
    first=(unsigned(read32(base+8)),unsigned(read32(base+12)))
    words=[unsigned(read32(base+4*i)) for i in range(100)]
    last=(unsigned(read32(base+8)),unsigned(read32(base+12)))
    if first != last or first != (words[2],words[3]): raise ValueError('Guest publication changed')
    if words[:2] != [0x42575251,1] or words[2] not in (2,3) or words[3] != sequence or words[4] != selector or words[5] > 6:
        raise ValueError('Missing, replaced or malformed guest publication')
    records=[]
    for i in range(words[5]):
        record=words[10+15*i:25+15*i]
        if record[2] not in (0,36,48): raise ValueError('Invalid guest output length')
        data=struct.pack('<12I',*record[3:])
        if data[record[2]:] != b'\0'*(48-record[2]): raise ValueError('Unexpected output tail')
        records.append({'result':signed(record[0]),'errno':record[1],'data':data[:record[2]]})
    return {'sequence':sequence,'selector':selector,'state':words[2],
            'open_result':signed(words[6]),'open_errno':words[7],
            'close_result':signed(words[8]),'close_errno':words[9],'records':records}


def mc_check_lump_mailbox(mailbox, output):
    """Actual inactive guest round trips; no queue, result or session writes."""
    from Antmicro.Renode.Core import EmulationManager
    from Antmicro.Renode.Time import TimeInterval
    from System import UInt64, UInt32
    mailbox,output=int(str(mailbox),0),int(str(output),0)
    extent(mailbox,32); extent(output,400)
    if max(mailbox,output) < min(mailbox+32,output+400): raise ValueError('Request/result extents overlap')
    machine=monitor.Machine
    if not machine.IsPaused: raise ValueError('Guest must start paused')
    # Separate the startup publication from the next worker scheduling interval.
    EmulationManager.Instance.CurrentEmulation.RunFor(TimeInterval.FromMilliseconds(UInt64(20)))
    if not machine.IsPaused: raise AssertionError('Guest did not pause after startup interval')
    read=lambda address: int(machine.SystemBus.ReadDoubleWord(UInt64(address)))
    write=lambda address,value: machine.SystemBus.WriteDoubleWord(UInt64(address),UInt32(value))
    for selector in (7,0,1):
        sequence=submit(mailbox,selector,read,write,machine.IsPaused)
        started=time.time(); response=None
        for elapsed in range(0,1001,10):
            if time.time()-started > 30: raise AssertionError('Diagnostic exceeded 30 host seconds')
            response=reply(mailbox,sequence,selector,read)
            if response is not None: break
            if elapsed == 1000: raise AssertionError('Diagnostic exceeded one guest second')
            EmulationManager.Instance.CurrentEmulation.RunFor(TimeInterval.FromMilliseconds(UInt64(10)))
            if not machine.IsPaused: raise AssertionError('Guest did not pause after diagnostic interval')
        if response['result'] != 0: raise AssertionError('Guest diagnostic refused: %r' % response)
        observed=publication(output,response['publication'],selector,read)
        if observed['state'] != 2 or observed['open_result'] < 0 or observed['open_errno'] or observed['close_result'] or observed['close_errno']:
            raise AssertionError('Guest diagnostic lifecycle failed: %r' % observed)
        expected=[]
        if selector == 7:
            expected=[{'result':-1,'errno':22 if i==0 else 14,'data':b''} for i in range(5)]
        expected.append({'result':-1,'errno':11,'data':b'\xa5'*(36 if selector==1 else 48)})
        if observed['records'] != expected: raise AssertionError('Guest diagnostic calls failed: %r' % observed)
        print('LUMP protected mailbox roundtrip passed: selector=%d sequence=%d publication=%d' % (selector,sequence,response['publication']))


class ActiveSessionFixture(object):
    """External electrical inputs plus the declared request ABI; no queue writes."""
    def __init__(self, mailbox, output, read, write, paused, advance, port,
                 clock=time.time, observe=None):
        self.mailbox, self.output = extent(mailbox,32), extent(output,400)
        if max(mailbox,output) < min(mailbox+32,output+400):
            raise ValueError('Request/result extents overlap')
        self.read,self.write,self.paused,self.advance,self.port,self.clock = read,write,paused,advance,port,clock
        if observe is None: raise ValueError('Read-only own-kernel queue observer required')
        self.observe,self.phase=observe,'admission'
        self.require_paused()
        if unsigned(read(mailbox+8)) != unsigned(read(mailbox+16)):
            raise RuntimeError('A diagnostic request is outstanding')

    def require_paused(self):
        if not self.paused(): raise ValueError('Active fixture requires paused emulation')

    def wait(self, predicate, limit_ms, description):
        started=self.clock()
        for elapsed in range(0,limit_ms+1,10):
            self.require_paused()
            if self.clock()-started > 120: raise AssertionError('Host deadline: '+description)
            result=predicate()
            if result:
                self.last_wait_ms=elapsed
                return result
            if elapsed == limit_ms: break
            self.advance(10)
        raise AssertionError('Guest deadline: '+description)

    def request(self, selector):
        self.require_paused()
        seq=submit(self.mailbox,selector,self.read,self.write,True)
        response=self.wait(lambda:reply(self.mailbox,seq,selector,self.read),1000,'mailbox reply')
        if response['result'] != 0: raise AssertionError('Guest request refused: %r' % response)
        observed=publication(self.output,response['publication'],selector,self.read)
        if observed['state'] != 2 or observed['open_result'] < 0 or observed['open_errno'] or observed['close_result'] or observed['close_errno']:
            raise AssertionError('Guest request lifecycle failed: %r' % observed)
        return observed['records']

    def attach(self):
        self.require_paused()
        self.port.Attach('ultrasonic')
        self.port.SetDataReportBudget(0)
        self.wait(lambda:str(self.port.State)=='Streaming',5000,'genuine F synchronization')
        if int(self.port.Device.TypeId)!=62 or int(self.port.SelectedMode)!=0:
            raise AssertionError('Unexpected synchronized F device or mode')

    def emit(self, distance):
        self.require_paused()
        if str(self.port.State)!='Streaming': raise AssertionError('F lost synchronization')
        if int(self.port.BridgeDrive)!=0: raise AssertionError('Sensor fixture observed motor drive')
        self.phase='emit-%d' % distance
        before=int(self.port.TransmittedFrames)
        timeouts=int(self.port.Timeouts)
        self.port.Device.SetDistance(distance)
        self.port.SetDataReportBudget(1)
        self.wait(lambda:int(self.port.DataReportsRemaining)==0,200,'one external DATA report')
        # Allow normal UART/DMA and kernel scheduling to deliver the emitted bytes.
        self.advance(10)
        self.require_paused()
        if (str(self.port.State)!='Streaming' or int(self.port.Timeouts)!=timeouts
                or int(self.port.TransmittedFrames)!=before+1):
            raise AssertionError('External DATA emission or synchronization changed')
        def admitted():
            state=self.observe()
            return state if (state is not None and state['active'] and state['count']==1
                and state['frame']==self.frame(distance) and not state['dropped']) else None
        return self.wait(admitted,200,'actual F queue admission '+str(distance))

    @staticmethod
    def frame(distance):
        return b'\x00\x02\x00\x00'+struct.pack('<H',distance)+b'\x00'*30

    def success(self, records, distance, legacy=False, invalid=False):
        faults=[{'result':-1,'errno':22 if i==0 else 14,'data':b''} for i in range(5)] if invalid else []
        if len(records)!=len(faults)+1 or records[:len(faults)]!=faults:
            raise AssertionError('Unexpected invalid-call record sequence')
        record=records[-1]
        if record['result'] or record['errno']: raise AssertionError('Expected queued DATA: %r' % record)
        data=record['data']
        if legacy:
            if data!=self.frame(distance): raise AssertionError('Legacy DATA mismatch')
            return None
        if len(data)!=48: raise AssertionError('Session DATA extent mismatch')
        session=struct.unpack('<Q',data[:8])[0]
        if not session or data[8:]!=self.frame(distance)+b'\x00'*4:
            raise AssertionError('Session identity, payload or reserved bytes mismatch')
        return session

    def empty(self):
        expected=[{'result':-1,'errno':11,'data':b'\xa5'*48}]
        actual=self.request(0)
        if actual!=expected:
            raise AssertionError('Expected unchanged empty session poll: phase=%s actual=%r queue=%r' % (self.phase,actual,self.observe()))

    def run(self):
        self.attach()
        admitted=self.emit(1111)
        first=self.success(self.request(7),1111,invalid=True)
        if first!=admitted['session']:raise AssertionError('Admitted session changed during invalid batch')
        self.phase='empty-after-invalid-batch'
        self.empty()
        self.emit(2222)
        self.success(self.request(1),2222,legacy=True)
        self.phase='empty-after-legacy'
        self.empty()
        self.emit(3333)
        stable=self.success(self.request(0),3333)
        if stable!=first: raise AssertionError('Identity changed within a live F session')
        self.emit(4444)
        self.port.Detach()
        self.phase='detach-invalidation'
        def inactive():
            state=self.observe()
            return state if state is not None and not state['active'] and state['count']==0 else None
        self.wait(inactive,5000,'actual F queue invalidation after detach')
        detach_wait=self.last_wait_ms
        self.empty()
        self.attach()
        self.emit(5555)
        replaced=self.success(self.request(0),5555)
        if replaced<=first: raise AssertionError('Same-type replacement reused an F identity')
        self.phase='empty-after-replacement'
        self.empty()
        if int(self.port.BridgeDrive)!=0: raise AssertionError('Sensor fixture left motor drive')
        return {'firstSession':first,'replacementSession':replaced,'requests':8,'externalReports':5,'detachWaitMs':detach_wait}


def mc_check_lump_active(mailbox, output, layout_path, kernel_path, queue_symbol):
    """Actual F inputs and worker requests on a separately staged compiled board."""
    from Antmicro.Renode.Core import EmulationManager
    from Antmicro.Renode.Time import TimeInterval
    from System import UInt64, UInt32
    import hashlib
    import json
    with open(str(kernel_path).lstrip('@'),'rb') as source: digest=hashlib.sha256(source.read()).hexdigest()
    with open(str(layout_path).lstrip('@')) as source: layout=json.load(source)
    machine=monitor.Machine
    observer=LumpQueueObserver(layout,digest,int(str(queue_symbol),0),
        lambda address:int(machine.SystemBus.ReadByte(UInt64(address))),lambda:machine.IsPaused)
    port=machine['sysbus.uart9.portF']
    advance=lambda ms:EmulationManager.Instance.CurrentEmulation.RunFor(TimeInterval.FromMilliseconds(UInt64(ms)))
    fixture=ActiveSessionFixture(int(str(mailbox),0),int(str(output),0),
        lambda address:int(machine.SystemBus.ReadDoubleWord(UInt64(address))),
        lambda address,value:machine.SystemBus.WriteDoubleWord(UInt64(address),UInt32(value)),
        lambda:machine.IsPaused,advance,port,observe=observer.snapshot)
    result=fixture.run()
    print('LUMP active F session fixture passed: %r' % result)
