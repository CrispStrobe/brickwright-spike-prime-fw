#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the harness's actual process-group cleanup without Bluetooth deps."""
import ast
import asyncio
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'simulation/bluetooth-air/test_spike_air.py'
parsed = ast.parse(SOURCE.read_text())
function = next(node for node in parsed.body if isinstance(node, ast.AsyncFunctionDef)
                and node.name == 'stop_owned_process')
scope = dict(asyncio=asyncio, os=os, signal=signal, subprocess=subprocess, Path=Path)
exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), 'exec'), scope)
stop_owned_process = scope['stop_owned_process']
air_function = next(node for node in parsed.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'air_tools')
exec(compile(ast.Module(body=[air_function], type_ignores=[]), str(SOURCE), 'exec'), scope)
air_tools = scope['air_tools']


class ToolSelection(unittest.TestCase):
    def test_explicit_air_tools_wins_in_either_cli_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'runtime'
            (runtime / 'tools/bw-air').mkdir(parents=True)
            override = root / 'selected-air'
            override.mkdir()
            for arguments in (['--renode', str(runtime), '--air-tools', str(override)],
                              ['--air-tools', str(override), '--renode', str(runtime)]):
                self.assertEqual(air_tools(arguments), override.resolve())
            self.assertEqual(air_tools(['--renode', str(runtime)]),
                             (runtime / 'tools/bw-air').resolve())


class ProcessCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_exited_shell_leader_does_not_leave_worker_running(self):
        await self._assert_background_worker_stopped()

    async def test_exited_leader_does_not_leave_term_ignoring_worker(self):
        await self._assert_background_worker_stopped(ignore_term=True)

    async def _assert_background_worker_stopped(self, ignore_term=False):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'worker-progress'
            worker = ('import pathlib,time,sys,signal; '
                      + ('signal.signal(signal.SIGTERM,signal.SIG_IGN); ' if ignore_term else '')
                      + 'p=pathlib.Path(sys.argv[1]); '
                      '\nwhile True:\n with p.open("ab") as f: f.write(b".")\n time.sleep(.01)')
            command = '%s -c %s %s &' % (shlex.quote(sys.executable),
                                         shlex.quote(worker), shlex.quote(str(marker)))
            process = await asyncio.create_subprocess_shell(command,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
            try:
                await asyncio.wait_for(process.wait(), 2)
                self.assertEqual(process.returncode, 0)
                async with asyncio.timeout(2):
                    while not marker.exists() or marker.stat().st_size < 2:
                        await asyncio.sleep(.01)
                await stop_owned_process(process)
                await asyncio.sleep(.1)
                size = marker.stat().st_size
                await asyncio.sleep(.15)
                self.assertEqual(marker.stat().st_size, size,
                                 'Exited group leader left owned background worker running')
                await stop_owned_process(process)  # already-cleaned group is safe
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                await process.wait()

    async def test_live_group_leader_is_reaped_and_repeat_cleanup_is_safe(self):
        process = await asyncio.create_subprocess_exec(sys.executable, '-c',
                    'import time; time.sleep(60)', start_new_session=True)
        try:
            await stop_owned_process(process)
            self.assertIsNotNone(process.returncode)
            await stop_owned_process(process)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            await process.wait()


if __name__ == '__main__':
    unittest.main()
