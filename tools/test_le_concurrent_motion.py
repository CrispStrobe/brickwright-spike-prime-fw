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


class Overlap(unittest.TestCase):
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
