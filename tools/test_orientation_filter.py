#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise the actual firmware filter with independent synthetic motion."""
import ctypes
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
V3 = ctypes.c_float * 3
Q4 = ctypes.c_float * 4


class OrientationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        folder = Path(cls.temp.name)
        source = folder / 'adapter.c'
        source.write_text('#include "drivebase_orientation.h"\n'
                          'void step(float *q, const float *a, const float *g, float dt, float gain)'
                          '{ db_orientation_update(q, a, g, dt, gain); }\n')
        lib = folder / 'filter.so'
        subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared',
                        '-fPIC', '-I', str(ROOT / 'apps/drivebase'), str(source),
                        '-o', str(lib), '-lm'], check=True)
        cls.library = ctypes.CDLL(str(lib))
        cls.step = cls.library.step
        cls.step.argtypes = [Q4, V3, V3, ctypes.c_float, ctypes.c_float]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def close_rotation(self, actual, expected, tolerance=2e-4):
        error = min(sum((actual[i] - sign * expected[i]) ** 2 for i in range(4))
                    for sign in (1, -1)) ** 0.5
        self.assertLess(error, tolerance)
        self.assertAlmostEqual(sum(v*v for v in actual), 1, places=5)

    def test_freefall_rotation_about_each_axis(self):
        for axis in range(3):
            q = Q4(1, 0, 0, 0)
            rate = [0, 0, 0]
            rate[axis] = math.pi/2
            for _ in range(100):
                self.step(q, V3(0, 0, 0), V3(*rate), .01, .5)
            expected = [math.sqrt(.5), 0, 0, 0]
            expected[axis+1] = math.sqrt(.5)
            self.close_rotation(q, expected)

    def test_tilted_world_yaw_preserves_gravity_alignment(self):
        tilt = math.radians(51)
        q = Q4(math.cos(tilt/2), math.sin(tilt/2), 0, 0)
        acceleration = V3(0, math.sin(tilt), math.cos(tilt))
        gyro = V3(0, math.sin(tilt)*math.pi/2, math.cos(tilt)*math.pi/2)
        for n in range(400):
            self.step(q, acceleration, gyro, .01, .5)
            if n == 99:
                # World-Z quarter turn multiplied by the starting X tilt.
                h = math.sqrt(.5)
                self.close_rotation(q, [h*math.cos(tilt/2), h*math.sin(tilt/2),
                                        h*math.sin(tilt/2), h*math.cos(tilt/2)])
        self.close_rotation(q, [math.cos(tilt/2), math.sin(tilt/2), 0, 0])

    def test_gravity_convergence_small_and_large_errors(self):
        for degrees in (30, 150):
            angle = math.radians(degrees)
            q = Q4(1, 0, 0, 0)
            accel = V3(0, math.sin(angle), math.cos(angle))
            for _ in range(6000):
                self.step(q, accel, V3(0, 0, 0), .01, .5)
            self.close_rotation(q, [math.cos(angle/2), math.sin(angle/2), 0, 0])

    def test_zero_gain_disables_acceleration_correction(self):
        q = Q4(1, 0, 0, 0)
        for _ in range(100):
            self.step(q, V3(0, 1, 0), V3(0, 0, 0), .01, 0)
        self.close_rotation(q, [1, 0, 0, 0])

    def test_invalid_samples_do_not_corrupt_state(self):
        for dt, gain, accel, gyro in [
            (0, .5, (0, 0, 1), (0, 0, 1)),
            (-1, .5, (0, 0, 1), (0, 0, 1)),
            (float('nan'), .5, (0, 0, 1), (0, 0, 1)),
            (.01, -1, (0, 0, 1), (0, 0, 1)),
            (.01, .5, (0, float('nan'), 1), (0, 0, 1)),
            (.01, .5, (0, 0, 1), (0, 0, float('inf'))),
        ]:
            q = Q4(1, 0, 0, 0)
            self.step(q, V3(*accel), V3(*gyro), dt, gain)
            self.close_rotation(q, [1, 0, 0, 0])


if __name__ == '__main__':
    unittest.main()
