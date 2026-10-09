# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Finite E/F external-input experiment, with only fixed mailbox requests."""
import time
try:
    from lump_request_transport import ActiveSessionFixture
    from lump_data_feeder import BoundedDataFeeder
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
        self.elapsed_ms=0
        def advance_all(ms):
            advance(ms)
            self.elapsed_ms+=ms
        self.fixtures={name:ActiveSessionFixture(mailbox,output,read,write,paused,
            advance_all,ports[name],clock,observe=observers[name]) for name in ('E','F')}
        self.requests=0

    def pending(self, name, distance, session, checkpoint="direct-check", count=1):
        f=self.fixtures[name]
        def unchanged():
            state=f.observe()
            return state if (state is not None and state['active'] and state['count']==count
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

    def sustained_window(self, session, seed, first_distance, operation):
        e,f=self.fixtures['E'],self.fixtures['F']
        feeder=BoundedDataFeeder(f,session,seed,first_distance,simulated_time=lambda:self.elapsed_ms)
        original=e.advance
        e.advance=feeder.advance
        try:
            operation()
            distances=feeder.settle()
        finally:
            e.advance=original
        self.keepalive_reports+=feeder.issued
        self.quiet_drains.append(feeder)
        return feeder,distances

    def drain(self, feeder, distances, e_pending=None):
        f=self.fixtures['F'];original=f.advance
        f.advance=feeder.drain_step
        try:
            for index,distance in enumerate(distances):
                if self.poll('F',distance)!=feeder.session:
                    raise AssertionError('Continued DATA drain changed F identity')
                f.wait(lambda:feeder.check(distances[index+1:]),200,'ordered continued DATA drain')
                if e_pending is not None:self.pending('E',e_pending[0],e_pending[1],'after-F-keepalive-drain')
            self.empty('F')
            feeder.drain_ms=feeder.now()-feeder.last_admission_ms
        finally:
            f.advance=original

    def run_silence(self):
        e,f=self.fixtures['E'],self.fixtures['F']
        if str(e.port.State)!='Detached':raise AssertionError('Silence control requires detached E')
        f.attach();admitted=f.emit(12345)
        frames=int(f.port.TransmittedFrames);timeouts=int(f.port.Timeouts)
        def inactive():
            state=f.observe()
            return state if state is not None and not state['active'] and state['count']==0 else None
        invalidated=f.wait(inactive,5000,'F DATA silence invalidation without E activity')
        elapsed=f.last_wait_ms
        if invalidated['session']!=admitted['session'] or invalidated['dropped']:
            raise AssertionError('Silence control replaced its session or dropped DATA')
        if (str(f.port.State)!='Streaming' or int(f.port.DataReportsRemaining)!=0
                or int(f.port.TransmittedFrames)!=frames or int(f.port.Timeouts)!=timeouts
                or int(f.port.BridgeDrive)!=0 or str(e.port.State)!='Detached'):
            raise AssertionError('Silence control changed external topology or input')
        self.empty('F');f.port.Detach();f.advance(5000);f.require_paused()
        return {'silentSession':admitted['session'],'invalidationMs':elapsed,
            'externalReports':1,'requests':self.requests,'modelTimeouts':timeouts,
            'modelStateAtInvalidation':'Streaming','eStateAtInvalidation':'Detached'}

    def run(self):
        e,f=self.fixtures['E'],self.fixtures['F']
        self.keepalive_reports=0;self.quiet_drains=[]
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
        def detach_e():
            e.emit(7777);e.port.Detach()
            def inactive():
                state=e.observe()
                return state if state is not None and not state['active'] and state['count']==0 else None
            e.wait(inactive,5000,'E actual queue invalidation')
        first,distances=self.sustained_window(sf,[5555],9001,detach_e)
        detached_ms=e.last_wait_ms
        self.pending('F',5555,sf,'after-E-detach',count=len(distances))
        self.empty('E');self.pending('F',5555,sf,'after-E-empty-after-detach',count=len(distances))
        self.drain(first,distances)
        replacement_state=[]
        def replace_e():
            e.attach();replacement_state.append(e.emit(8888))
        second,distances=self.sustained_window(sf,[],9101,replace_e)
        replacement=replacement_state[0]['session']
        if replacement<=se:raise AssertionError('E replacement identity did not progress')
        self.drain(second,distances,e_pending=(8888,replacement))
        f.emit(9999)
        if self.poll('E',8888)!=replacement:raise AssertionError('E replacement reply identity mismatch')
        self.pending('F',9999,sf,'after-E-replacement-poll')
        if self.poll('F',9999)!=sf:raise AssertionError('E replacement changed F identity')
        self.empty('E');self.empty('F')
        if any(int(x.port.BridgeDrive)!=0 for x in (e,f)):
            raise AssertionError('Sensor fixture left motor drive')
        return {'ports':['E','F'],'requests':self.requests,'externalReports':9+self.keepalive_reports,'keepaliveReports':self.keepalive_reports,
            'firstE':se,'replacementE':replacement,'stableF':sf,'detachWaitMs':detached_ms,
            'quietDrainMs':[x.drain_ms for x in self.quiet_drains]}


def actual_fixture(mailbox, output, layout_path, kernel_path, queue_symbol):
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
    return fixture


def mc_check_lump_two_port(mailbox, output, layout_path, kernel_path, queue_symbol):
    print('LUMP two-port isolation fixture passed: %r' % actual_fixture(mailbox,output,layout_path,kernel_path,queue_symbol).run())


def mc_check_lump_silence(mailbox, output, layout_path, kernel_path, queue_symbol):
    print('LUMP F DATA silence control passed: %r' % actual_fixture(mailbox,output,layout_path,kernel_path,queue_symbol).run_silence())
