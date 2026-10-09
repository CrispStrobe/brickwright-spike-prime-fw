# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Finite external DATA stimulus; observe admission, never mutate guest queues."""


class BoundedDataFeeder(object):
    def __init__(self, fixture, session, distances, first_distance, report_cap=12, simulated_time=None):
        if type(report_cap) is not int or not 1<=report_cap<=12:
            raise ValueError('Finite report cap required')
        self.fixture,self.session=fixture,session
        self.distances=list(distances)
        self.advance_guest=fixture.advance
        self.clock=fixture.clock
        self.started=self.clock()
        self.elapsed=0
        self.now=simulated_time if simulated_time is not None else lambda:self.elapsed
        self.next_due=self.now();self.enabled=True
        self.cap=report_cap;self.issued=0;self.first_distance=first_distance
        self.pending=None;self.last_admission_ms=self.now();self.drain_ms=0
        self.check(self.distances)

    def check(self, distances):
        self.fixture.require_paused()
        state=self.fixture.observe()
        if state is None:return None
        front=self.fixture.frame(distances[0]) if distances else None
        if (not state['active'] or state['session']!=self.session or state['dropped']
                or state['count']!=len(distances) or state['frame']!=front):
            raise AssertionError('Continued DATA queue changed: expected=%r session=%d actual=%r' % (distances,self.session,state))
        return state

    def advance(self, ms):
        if type(ms) is not int or not 1<=ms<=10:
            raise ValueError('Feeder requires bounded guest steps')
        f=self.fixture;f.require_paused()
        if self.clock()-self.started>120:raise AssertionError('Host DATA feeder deadline')
        if self.enabled and self.pending is None and self.now()>=self.next_due:
            if self.issued>=self.cap:raise AssertionError('External DATA report cap exhausted')
            if self.check(self.distances) is not None:
                if str(f.port.State)!='Streaming' or int(f.port.BridgeDrive)!=0 or int(f.port.DataReportsRemaining)!=0:
                    raise AssertionError('Unexpected continued DATA model state or pending budget')
                distance=self.first_distance+self.issued
                self.pending={'distance':distance,'started':self.now(),
                    'frames':int(f.port.TransmittedFrames),'timeouts':int(f.port.Timeouts)}
                f.port.Device.SetDistance(distance);f.port.SetDataReportBudget(1)
                self.issued+=1;self.next_due=self.now()+200
        self.advance_guest(ms);self.elapsed+=ms;f.require_paused()
        if self.pending is not None:
            report=self.pending
            if self.now()-report['started']>200:raise AssertionError('Continued DATA admission deadline')
            if str(f.port.State)!='Streaming' or int(f.port.BridgeDrive)!=0 or int(f.port.Timeouts)!=report['timeouts']:
                raise AssertionError('Continued DATA lost model synchronization')
            if int(f.port.DataReportsRemaining)==0:
                if int(f.port.TransmittedFrames)!=report['frames']+1:
                    raise AssertionError('Continued DATA transmission count mismatch')
                state=f.observe()
                if state is not None:
                    # A completed model transmission may still be in UART/DMA.
                    if state['count']==len(self.distances):self.check(self.distances)
                    else:
                        expected=self.distances+[report['distance']]
                        if self.check(expected) is not None:
                            self.distances=expected;self.pending=None
                            self.last_admission_ms=self.now()

    def settle(self):
        self.enabled=False
        if not self.issued:raise AssertionError('No continued DATA report issued')
        for _ in range(21):
            if self.pending is None and self.check(self.distances) is not None:return list(self.distances)
            self.advance(10)
        raise AssertionError('Continued DATA settle deadline')

    def drain_step(self, ms):
        # All reports have been admitted; no further emission during drain.
        if self.pending is not None or self.enabled:raise AssertionError('Cannot drain an active feeder')
        if self.now()+ms-self.last_admission_ms>400:
            raise AssertionError('Quiet drain exceeded time since last DATA admission')
        self.advance_guest(ms);self.elapsed+=ms
