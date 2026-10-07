#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Check the actual LE caller budgets its required reconnect observation."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation/bluetooth-air"))
from spike_timeouts import le_round_trip_budget


class Bounds(unittest.TestCase):
    def test_ordinary_and_capped_observation_bounds(self):
        self.assertEqual(le_round_trip_budget(), 180)
        self.assertEqual(le_round_trip_budget(True), 300)
        self.assertEqual(le_round_trip_budget(True, 10000), 600)

    def test_invalid_window_cannot_make_an_unbounded_wait(self):
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                le_round_trip_budget(True, value)


class Caller(unittest.IsolatedAsyncioTestCase):
    async def test_required_quiet_observation_fits_actual_caller_budget(self):
        # Actual incomplete run: prior silence, three samples, unsubscribe
        # silence and protocol overhead exceed the old 300-second phase.
        required = 106.871 + 77.419 + 112.590 + 20
        captured = []
        class Entered(Exception):
            pass
        class Timeout:
            def __init__(self, seconds):
                captured.append(seconds)
            async def __aenter__(self):
                raise Entered()
            async def __aexit__(self, *args):
                return False
        source = ROOT / "simulation/bluetooth-air/test_spike_air.py"
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "le_round_trip")
        scope = dict(asyncio=SimpleNamespace(timeout=Timeout),
                     le_round_trip_budget=le_round_trip_budget)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), scope)
        with self.assertRaises(Entered):
            await scope["le_round_trip"](None, None, {}, periodic=True,
                                          reconnect_quiet=106.871)
        self.assertGreaterEqual(captured[0], required)
        self.assertLessEqual(captured[0], 600)


if __name__ == "__main__":
    unittest.main()
