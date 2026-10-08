# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Finite E/F external-input experiment, with only fixed mailbox requests."""
import time
try:
    from lump_request_transport import ActiveSessionFixture
except ImportError:
    # Renode includes the reviewed transport in the same monitor scope first.
    pass


class TwoPortFixture(object):
    def __init__(self, mailbox, output, read, write, paused, advance, ports,
                 observers, clock=time.time):
        if set(ports)!=set(('E','F')) or set(observers)!=set(('E','F')):
            raise ValueError('Exactly the declared E/F ports and observers required')
        if ports['E'] is ports['F'] or observers['E'] is observers['F']:
            raise ValueError('Distinct ports and observers required')
        self.fixtures={name:ActiveSessionFixture(mailbox,output,read,write,paused,
            advance,ports[name],clock,observe=observers[name]) for name in ('E','F')}
        self.requests=0

    def pending(self, name, distance, session, checkpoint="direct-check"):
        f=self.fixtures[name]
        def unchanged():
            state=f.observe()
            return state if (state is not None and state['active'] and state['count']==1
                and state['frame']==f.frame(distance) and state['session']==session
                and not state['dropped']) else None
        description='%s unchanged pending payload/session checkpoint=%s request=%d distance=%d session=%d' % (name,checkpoint,self.requests,distance,session)
        try:
            return f.wait(unchanged,200,description)
        except AssertionError as failure:
            try:
                diagnostic='queue=%r modelState=%s timeouts=%d transmitted=%d budget=%d drive=%d' % (
                    f.observe(),f.port.State,int(f.port.Timeouts),int(f.port.TransmittedFrames),
                    int(f.port.DataReportsRemaining),int(f.port.BridgeDrive))
            except Exception as sampling_error:
                diagnostic='diagnostic sampling failed: %s' % sampling_error
            raise AssertionError('%s; %s' % (failure,diagnostic))

    def poll(self, name, distance, invalid=False):
        f=self.fixtures[name]
        selector=(9 if invalid else 8) if name=='E' else (7 if invalid else 0)
        self.requests+=1
        return f.success(f.request(selector),distance,invalid=invalid)

    def empty(self, name):
        f=self.fixtures[name]
        self.requests+=1
        actual=f.request(8 if name=='E' else 0)
        if actual!=[{'result':-1,'errno':11,'data':b'\xa5'*48}]:
            raise AssertionError(name+' empty poll changed output or returned DATA')

    def run(self):
        e,f=self.fixtures['E'],self.fixtures['F']
        # Attach sequentially; both then remain active during the interleaving.
        f.attach();e.attach()
        sf=f.emit(1111)['session'];se=e.emit(2222)['session']
        if self.poll('F',1111)!=sf:raise AssertionError('F admitted identity mismatch')
        self.pending('E',2222,se,'after-F1111-poll')
        if self.poll('E',2222)!=se:raise AssertionError('E admitted identity mismatch')
        f.emit(3333);e.emit(4444)
        if self.poll('E',4444)!=se:raise AssertionError('E live identity changed')
        self.pending('F',3333,sf,'after-E4444-poll')
        if self.poll('F',3333)!=sf:raise AssertionError('F live identity changed')
        f.emit(5555);e.emit(6666)
        if self.poll('E',6666,invalid=True)!=se:raise AssertionError('E refusal batch identity changed')
        self.pending('F',5555,sf,'after-E-invalid-batch')
        self.empty('E');self.pending('F',5555,sf,'after-E-empty-before-detach')
        e.emit(7777);e.port.Detach()
        def inactive():
            state=e.observe()
            return state if state is not None and not state['active'] and state['count']==0 else None
        e.wait(inactive,5000,'E actual queue invalidation')
        detached_ms=e.last_wait_ms
        self.pending('F',5555,sf,'after-E-detach')
        self.empty('E');self.pending('F',5555,sf,'after-E-empty-after-detach')
        if self.poll('F',5555)!=sf:raise AssertionError('E detach changed F identity')
        e.attach();replacement=e.emit(8888)['session']
        if replacement<=se:raise AssertionError('E replacement identity did not progress')
        f.emit(9999)
        if self.poll('E',8888)!=replacement:raise AssertionError('E replacement reply identity mismatch')
        self.pending('F',9999,sf,'after-E-replacement-poll')
        if self.poll('F',9999)!=sf:raise AssertionError('E replacement changed F identity')
        self.empty('E');self.empty('F')
        if any(int(x.port.BridgeDrive)!=0 for x in (e,f)):
            raise AssertionError('Sensor fixture left motor drive')
        return {'ports':['E','F'],'requests':self.requests,'externalReports':9,
            'firstE':se,'replacementE':replacement,'stableF':sf,'detachWaitMs':detached_ms}


def mc_check_lump_two_port(mailbox, output, layout_path, kernel_path, queue_symbol):
    from Antmicro.Renode.Core import EmulationManager
    from Antmicro.Renode.Time import TimeInterval
    from System import UInt64, UInt32
    import hashlib
    import json
    with open(str(kernel_path).lstrip('@'),'rb') as source:digest=hashlib.sha256(source.read()).hexdigest()
    with open(str(layout_path).lstrip('@')) as source:layout=json.load(source)
    machine=monitor.Machine
    read8=lambda address:int(machine.SystemBus.ReadByte(UInt64(address)))
    paused=lambda:machine.IsPaused
    observers={name:LumpQueueObserver(layout,digest,int(str(queue_symbol),0),read8,paused,index)
        for name,index in (('E',4),('F',5))}
    ports={}
    for name in ('E','F'):
        matches=[str(path) for path in machine.GetAllNames() if str(path).endswith('.port'+name)]
        if len(matches)!=1:raise ValueError('Missing or ambiguous external port '+name)
        ports[name]=machine[matches[0]]
    fixture=TwoPortFixture(int(str(mailbox),0),int(str(output),0),
        lambda address:int(machine.SystemBus.ReadDoubleWord(UInt64(address))),
        lambda address,value:machine.SystemBus.WriteDoubleWord(UInt64(address),UInt32(value)),
        paused,lambda ms:EmulationManager.Instance.CurrentEmulation.RunFor(TimeInterval.FromMilliseconds(UInt64(ms))),
        ports,{name:observer.snapshot for name,observer in observers.items()})
    print('LUMP two-port isolation fixture passed: %r' % fixture.run())
