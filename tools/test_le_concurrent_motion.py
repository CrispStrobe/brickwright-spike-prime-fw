#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Do not infer notification/motion overlap from task scheduling alone."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation/bluetooth-air'))
from le_concurrent_motion import require_overlap
from classic_motor_probe import MotorPeer


class Overlap(unittest.TestCase):
    def test_invalid_ids_are_rejected_before_any_transport_write(self):
        class DLC:
            def write(self, data):
                raise AssertionError('Invalid request reached transport')
        peer = MotorPeer(DLC(), None, None, None, dict(requests=[]))
        for ident in ('la000', 'lm001', '', 'A001', 'a_01', 1):
            with self.assertRaisesRegex(ValueError, 'four lowercase'):
                peer.send(ident, 'scratch.motor_stop', {})

    def test_opposite_powered_motion_is_required_in_sample_observations(self):
        good = dict(motor_observations=[dict(power=30, speed=100), dict(power=-30, speed=-100)])
        require_overlap([good])
        for a, b in ((0, -100), (100, 0), (-100, 100), (100, 100)):
            with self.assertRaises(AssertionError):
                require_overlap([dict(motor_observations=[dict(power=30, speed=a), dict(power=-30, speed=b)])])
        for pa, pb in ((0, -30), (30, 0), (0, 0)):
            with self.assertRaises(AssertionError):
                require_overlap([dict(motor_observations=[dict(power=pa, speed=100), dict(power=pb, speed=-100)])])
        with self.assertRaises(AssertionError):
            require_overlap([])


if __name__ == '__main__':
    unittest.main()
