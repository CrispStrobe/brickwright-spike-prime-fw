#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic controls for external DATA/admission bookkeeping, not ARM tests."""
import io
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import lump_data_feeder as api
from test_lump_two_port import DualWorker


class Contract(unittest.TestCase):
    def setup_feeder(self, cap=12):
        w=DualWorker();pair=w.fixture();f=pair.fixtures['F'];f.attach();f.emit(5555)
        feeder=api.BoundedDataFeeder(f,1,[5555],9001,cap,lambda:pair.elapsed_ms)
        return w,pair,feeder
    def test_appends_are_observed_and_preserve_original_front(self):
        w,p,feed=self.setup_feeder()
        for _ in range(21):feed.advance(10)
        self.assertEqual(feed.settle(),[5555,9001,9002])
        self.assertEqual(feed.issued,2)
        self.assertEqual(w.workers['F'].queue,[p.fixtures['F'].frame(x) for x in (5555,9001,9002)])
        p.drain(feed,feed.distances)
        self.assertEqual(w.workers['F'].queue,[])
    def test_count_session_front_and_drop_corruption_are_rejected(self):
        for field,value in [('count',2),('session',2),('frame',b'wrong'),('dropped',1),('active',False)]:
            w,p,feed=self.setup_feeder();original=p.fixtures['F'].observe
            def observe():
                state=original();state[field]=value;return state
            p.fixtures['F'].observe=observe
            with self.subTest(field=field),self.assertRaises(AssertionError):feed.check([5555])
    def test_report_cap_does_not_turn_into_silent_remainder(self):
        w,p,feed=self.setup_feeder(cap=1)
        for _ in range(20):feed.advance(10)
        with self.assertRaisesRegex(AssertionError,'cap exhausted'):feed.advance(10)
    def test_model_transmission_without_admission_is_not_success(self):
        w,p,feed=self.setup_feeder();original=feed.advance_guest
        def missing(ms):
            original(ms)
            w.workers['F'].queue[:]=w.workers['F'].queue[:1]
        feed.advance_guest=missing
        with self.assertRaisesRegex(AssertionError,'admission deadline'):
            for _ in range(22):feed.advance(10)
    def test_unsolicited_append_is_refused(self):
        w,p,feed=self.setup_feeder();original=feed.advance_guest
        def duplicate(ms):
            original(ms);w.workers['F'].queue.append(p.fixtures['F'].frame(9001))
        feed.advance_guest=duplicate
        with self.assertRaisesRegex(AssertionError,'queue changed'):feed.advance(10)
    def test_quiet_drain_counts_other_ports_elapsed_time(self):
        w,p,feed=self.setup_feeder();feed.advance(10);feed.settle()
        p.fixtures['E'].advance(401)
        with self.assertRaisesRegex(AssertionError,'Quiet drain'):feed.drain_step(10)
    def test_pending_or_enabled_feeder_cannot_be_drained(self):
        w,p,feed=self.setup_feeder()
        with self.assertRaisesRegex(AssertionError,'active feeder'):feed.drain_step(10)
    def test_large_steps_and_invalid_caps_are_refused(self):
        w,p,feed=self.setup_feeder()
        for ms in (0,11,True,1.0):
            with self.assertRaises(ValueError):feed.advance(ms)
        for cap in (0,13,True):
            with self.assertRaises(ValueError):api.BoundedDataFeeder(p.fixtures['F'],1,[5555],9001,cap)
    def test_transient_none_between_admission_reads_is_not_success(self):
        w,p,feed=self.setup_feeder();original=p.fixtures['F'].observe;calls=[0]
        def observe():
            calls[0]+=1
            return None if calls[0]==3 else original()
        p.fixtures['F'].observe=observe
        feed.advance(10)
        self.assertIsNotNone(feed.pending)
        self.assertEqual(feed.distances,[5555])
        feed.advance(10)
        self.assertIsNone(feed.pending)
        self.assertEqual(feed.distances,[5555,9001])
    def test_permanent_none_reaches_admission_deadline(self):
        w,p,feed=self.setup_feeder();original=p.fixtures['F'].observe;calls=[0]
        def observe():
            calls[0]+=1
            return original() if calls[0]==1 else None
        p.fixtures['F'].observe=observe
        with self.assertRaisesRegex(AssertionError,'admission deadline'):
            for _ in range(22):feed.advance(10)
        self.assertEqual(feed.distances,[5555])
    def test_delayed_guest_admission_retains_pending_report(self):
        w,p,feed=self.setup_feeder();original=feed.advance_guest;held=[]
        initial=p.elapsed_ms
        def delayed(ms):
            original(ms)
            q=w.workers['F'].queue
            if len(q)>1 and p.elapsed_ms-initial<80:held.append(q.pop())
            if held and p.elapsed_ms-initial>=80:q.extend(held);held[:]=[]
        feed.advance_guest=delayed
        for _ in range(7):feed.advance(10)
        self.assertIsNotNone(feed.pending)
        self.assertEqual(feed.distances,[5555])
        feed.advance(10)
        self.assertEqual(feed.distances,[5555,9001])
        self.assertEqual(feed.issued,1)
    def test_twelve_report_window_stays_bounded_and_drains_in_order(self):
        w,p,feed=self.setup_feeder()
        for _ in range(221):feed.advance(10)
        distances=feed.settle()
        self.assertEqual(distances,[5555]+list(range(9001,9013)))
        self.assertEqual(feed.issued,12)
        p.drain(feed,distances)
        self.assertEqual(w.workers['F'].queue,[])
        self.assertLessEqual(feed.drain_ms,400)

    def test_actual_comparison_mutants_are_assertion_detected(self):
        source=Path(api.__file__).read_text()
        mutations={
            'ignore-count':("state['count']!=len(distances)",'False'),
            'ignore-session':("state['session']!=self.session",'False'),
            'ignore-front':("state['frame']!=front",'False'),
            'ignore-cap':('if self.issued>=self.cap:','if False:'),
            'ignore-quiet-time':('if self.now()+ms-self.last_admission_ms>400:','if False:'),
        }
        for name,(old,new) in mutations.items():
            self.assertEqual(source.count(old),1)
            mutant=ModuleType(name);exec(compile(source.replace(old,new),name,'exec'),mutant.__dict__)
            suite=unittest.TestSuite(Contract(test) for test in (
                'test_count_session_front_and_drop_corruption_are_rejected',
                'test_report_cap_does_not_turn_into_silent_remainder',
                'test_quiet_drain_counts_other_ports_elapsed_time'))
            with patch.dict(globals(),api=mutant):result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            self.assertEqual(result.errors,[],name+' setup exception is not detection')
            self.assertTrue(result.failures,name+' escaped assertions')

if __name__=='__main__':unittest.main()
