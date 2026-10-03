# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
# Synthetic CPU instructions and host-delayed notification; no firmware data.
import time
from System.Threading import Thread, ThreadStart

_observer_has_stopped = False
_observer_worker = None


def delayed_observer_log(r0, pc):
    # Controlled late delivery exposes WaitForEntry's implicit restart.
    time.sleep(2)
    monitor.Parse('log "SYNTHETIC return R0=%d PC=%d"' % (r0, pc))


def mc_prepare_milestone_wait_fixture():
    cpu = monitor.Machine['sysbus.cpu']
    bus = monitor.Machine['sysbus']
    # movs r0,#0 ; nop [observed site] ; movs r0,#7 ; b .
    bus.WriteWord(0x08000100, 0x2000)
    bus.WriteWord(0x08000102, 0xbf00)
    bus.WriteWord(0x08000104, 0x2007)
    bus.WriteWord(0x08000106, 0xe7fe)
    monitor.Parse('cpu PC 0x08000100')
    cpu.AddHook(0x08000102, stop_observer_at_return)


def mc_milestone_wait_fixture_stopped():
    print(bool(_observer_has_stopped and monitor.Machine['sysbus.cpu'].IsPaused))


def stop_observer_at_return(cpu, address):
    global _observer_has_stopped, _observer_worker
    # Retain real zero and site independently; no instruction is skipped.
    captured_r0 = int(cpu.GetRegister(0).RawValue)
    captured_pc = int(cpu.GetRegister(15).RawValue)
    if captured_r0 != 0 or captured_pc != 0x08000102:
        raise AssertionError('Synthetic return-state setup failed')
    monitor.Machine.PauseAndRequestEmulationPause(True)
    _observer_has_stopped = True
    worker = Thread(ThreadStart(lambda: delayed_observer_log(captured_r0, captured_pc)))
    worker.IsBackground = True
    _observer_worker = worker
    worker.Start()


def mc_finish_milestone_wait_fixture():
    # Await the producer before resetting the machine, including failed cases.
    # This fixture never leaves a delayed log producer running across tests.
    if _observer_worker is not None and not _observer_worker.Join(5000):
        raise AssertionError('Synthetic milestone producer failed to finish')
