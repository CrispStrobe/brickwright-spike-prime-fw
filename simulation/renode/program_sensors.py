# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Actual ARM service inputs: mailbox uploads and finite external UART reports.

Only the published program request fields are written in guest memory. Queue
observations are read-only and tied to the exact own-kernel ELF. No diagnostic
request, direct opener or class mode writer runs during this fixture.
"""
import struct
import time


def native_instructions(rows):
    return payload_bytes(b''.join(struct.pack('<4i', *row) for row in rows))


def python_reads_source(expected_e, expected_f):
    return ('import brickwright as b\n'
            'if b.sensor(1,b.E)!=%d: raise OSError(74)\n'
            'if b.sensor(2,b.F)!=%d: raise OSError(74)\n' %
            (expected_e, expected_f)).encode('ascii')


def sticky_python_source():
    return b'''import brickwright as b
if b.sensor(1,b.F)!=1234: raise OSError(74)
while True:
    try:
        b.sensor(1,b.F)
    except OSError as e:
        if e.args[0]==116: break
        if e.args[0]!=11: raise
    b.sleep_ms(20)
for i in range(3):
    try:
        b.sensor(1,b.F)
    except OSError as e:
        if e.args[0]!=116: raise
    else:
        raise OSError(74)
raise OSError(116)
'''


def mc_check_program_sensors(base, layout_path, kernel_path, queue_symbol):
    try:
        check_program_sensor_inputs(base, layout_path, kernel_path, queue_symbol)
    except Exception:
        import traceback
        print(traceback.format_exc())
        raise


def check_program_sensor_inputs(base, layout_path, kernel_path, queue_symbol):
    import hashlib
    import json
    from Antmicro.Renode.Core import EmulationManager
    from Antmicro.Renode.Time import TimeInterval
    from System import UInt64
    hub_machine = monitor.Machine
    started = time.time()
    elapsed = [0]
    reports = [0]
    if not hub_machine.IsPaused:
        raise AssertionError('Program sensor fixture requires paused guest')
    with open(str(kernel_path).lstrip('@'), 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    with open(str(layout_path).lstrip('@')) as source:
        layout = json.load(source)
    # Bind monitor objects outside the comprehension, as in the qualified
    # two-port fixture. Avoid relying on nested monitor-scope name resolution.
    read8 = lambda address, hub=hub_machine: int(hub.SystemBus.ReadByte(UInt64(address)))
    paused = lambda hub=hub_machine: hub.IsPaused
    observers = {name: LumpQueueObserver(layout, digest, int(str(queue_symbol), 0),
                 read8, paused, index) for name, index in (('E', 4), ('F', 5))}
    ports = {}
    for name in ('E', 'F'):
        matches = [str(path) for path in hub_machine.GetAllNames()
                   if str(path).endswith('.port' + name)]
        if len(matches) != 1:
            raise AssertionError('Missing or ambiguous external port ' + name)
        ports[name] = hub_machine[matches[0]]

    def advance():
        if elapsed[0] + 20 > 60000 or time.time() - started > 575:
            raise AssertionError('Program sensor fixture exceeded bounded execution')
        EmulationManager.Instance.CurrentEmulation.RunFor(TimeInterval.FromMilliseconds(UInt64(20)))
        elapsed[0] += 20
        if not hub_machine.IsPaused:
            raise AssertionError('RunFor did not pause sensor fixture')
        for port in ports.values():
            if int(port.BridgeDrive) != 0:
                raise AssertionError('Sensor program applied motor drive')

    client = ProgramWorkflow(hub_machine, base, advance)
    client.wait(lambda state: True, description='program worker publication')

    def wait(predicate, limit_ms, description):
        for spent in range(0, limit_ms + 1, 20):
            value = predicate()
            if value:
                return value
            if spent == limit_ms:
                break
            advance()
        raise AssertionError('Sensor fixture deadline: ' + description)

    def queue(name):
        state = observers[name].snapshot()
        if state is not None and state['dropped']:
            raise AssertionError('Sensor program lost external DATA')
        return state

    def attach(name, device='ultrasonic'):
        port = ports[name]
        if str(port.State) != 'Detached':
            raise AssertionError('Attachment requires declared detached port')
        port.Attach(device)
        port.SetDataReportBudget(0)
        wait(lambda: str(port.State) == 'Streaming', 5000, name + ' synchronization')
        expected_type = 62 if device == 'ultrasonic' else 61
        if int(port.Device.TypeId) != expected_type or int(port.SelectedMode) != 0:
            raise AssertionError('Unexpected ultrasonic identity/mode')
        def active():
            state = queue(name)
            return state if state is not None and state['active'] and not state['count'] else None
        return wait(active, 200, name + ' empty synchronized guest queue')['session']

    def detach(name):
        ports[name].Detach()
        def inactive():
            state = queue(name)
            return state if state is not None and not state['active'] and not state['count'] else None
        wait(inactive, 5000, name + ' queue invalidation')

    def emit(name, distance, pending=True):
        port = ports[name]
        if str(port.State) != 'Streaming' or int(port.DataReportsRemaining) != 0:
            raise AssertionError('Report requires synchronized idle model')
        if reports[0] >= 24:
            raise AssertionError('Finite external report cap exhausted')
        frames, timeouts = int(port.TransmittedFrames), int(port.Timeouts)
        port.Device.SetDistance(distance)
        port.SetDataReportBudget(1)
        reports[0] += 1
        wait(lambda: int(port.DataReportsRemaining) == 0, 200, name + ' report transmission')
        if (int(port.TransmittedFrames) != frames + 1 or
                int(port.Timeouts) != timeouts or str(port.State) != 'Streaming'):
            raise AssertionError('External UART transmission lost synchronization')
        if pending:
            expected = b'\x00\x02\x00\x00' + struct.pack('<H', distance) + b'\x00' * 30
            def admitted():
                state = queue(name)
                return state if (state is not None and state['active'] and
                    state['count'] == 1 and state['frame'] == expected) else None
            return wait(admitted, 200, name + ' exact admitted payload')['session']

    def consumed(name):
        def empty():
            state = queue(name)
            return state if state is not None and state['active'] and not state['count'] else None
        return wait(empty, 200, name + ' actual program consumption')

    def terminal(ident, state=3, error=0):
        result = client.wait(lambda s: s['id'] == ident and s['state'] == state,
                             description='sensor program terminal state')
        if result['error'] != error:
            raise AssertionError('Wrong program error: %r' % result)
        return result

    def prepare(ident, payload, python=False, names=('E', 'F'), device='ultrasonic'):
        # Upload can take longer than a DATA-silent attachment stays active.
        # Reset only external inputs while terminal; attach after upload so
        # each trial starts with explicitly empty, freshly synchronized queues.
        for name in ('E', 'F'):
            if str(ports[name].State) != 'Detached':
                detach(name)
        client.upload(ident, payload, python=python)
        return {name: attach(name, device) for name in names}

    # Opposite polarity and independent ports; each consumes its exact report.
    ident = 0x3501
    initial = prepare(ident, native_instructions([(3, 0x121, 1200, 0),
                                            (3, 0x12a, 1200, 0), (0, 0, 0, 0)]))
    first_e, first_f = initial['E'], initial['F']
    emit('E', 1111); emit('F', 1500)
    client.start(ident); terminal(ident); consumed('E'); consumed('F')
    # Unknown does not satisfy a comparison. STOP cancels the waiting program.
    ident = 0x3502
    prepare(ident, native_instructions([(3, 0x121, 65535, 0), (0, 0, 0, 0)]), names=('E',))
    emit('E', 65535); client.start(ident); consumed('E')
    for unused in range(5): advance()
    state = client.snapshot()
    if state is None or state['state'] != 2 or state['pc'] != 0:
        raise AssertionError('Unknown distance incorrectly satisfied native wait')
    client.exchange(4, ident); terminal(ident, 4)
    # Embedded Python observes exact E/F signed millimetres, including unknown.
    ident = 0x3503
    prepare(ident, payload_bytes(python_reads_source(4321, -1)), python=True)
    emit('E', 4321); emit('F', 65535)
    client.start(ident, allow_unwind=True); terminal(ident); consumed('E'); consumed('F')
    # Active synchronization without DATA produces EAGAIN in actual Python.
    ident = 0x3507
    no_data = b"""import brickwright as b
for port in (b.E,b.F):
    try:
        b.sensor(1,port)
    except OSError as e:
        if e.args[0]!=11: raise
    else:
        raise OSError(74)
"""
    empty_sessions = prepare(ident, payload_bytes(no_data), python=True)
    def unchanged_empty_sessions():
        for name, session in empty_sessions.items():
            state = queue(name)
            if (state is None or not state['active'] or state['count'] or
                    state['session'] != session or str(ports[name].State) != 'Streaming'):
                raise AssertionError('No-DATA trial lost synchronization/session')
    unchanged_empty_sessions()
    client.start(ident, allow_unwind=True); terminal(ident)
    unchanged_empty_sessions()
    # Reject a synchronized color device through the actual Python callback.
    ident = 0x3508
    wrong_type = b"""import brickwright as b
try:
    b.sensor(1,b.F)
except OSError as e:
    if e.args[0]!=19: raise
else:
    raise OSError(74)
"""
    color_session = prepare(ident, payload_bytes(wrong_type), python=True,
                            names=('F',), device='color')['F']
    client.start(ident, allow_unwind=True); terminal(ident)
    color = queue('F')
    if (color is None or not color['active'] or color['count'] or
            color['session'] != color_session or str(ports['F'].State) != 'Streaming' or
            int(ports['F'].Device.TypeId) != 61):
        raise AssertionError('Wrong-type trial lost its synchronized color identity')
    # Each true/false conditional chooses a different finite WAIT witness.
    # Known/unknown DATA must be consumed, so missing DATA cannot masquerade as
    # the false comparison. The target skips the 500-ms false-path WAIT.
    conditional_trials = ((0x121, 1000, 999, True),
                          (0x121, 1000, 1000, False),
                          (0x122, 1000, 1001, True),
                          (0x122, 1000, 1000, False),
                          (0x121, 65535, 65535, False),
                          (0x122, 0, 65535, False))
    for trial, (selector, threshold, distance, takes_jump) in enumerate(conditional_trials):
        ident = 0x3520 + trial
        prepare(ident, native_instructions([(5, selector, threshold, 3),
                (2, 500, 0, 0), (4, 4, 0, 0), (2, 500, 0, 0), (0, 0, 0, 0)]),
                names=('E',))
        emit('E', distance); client.start(ident); consumed('E')
        witness = client.wait(lambda x: x['id'] == ident and x['state'] == 2 and
                              x['pc'] in (2, 4), 200, 'conditional WAIT witness')
        if witness['pc'] != (4 if takes_jump else 2):
            raise AssertionError('Conditional selected the wrong branch: %r' % witness)
        client.exchange(4, ident); terminal(ident, 4)
    # A fresh native reader binds F; an identical replacement payload is stale.
    ident = 0x3504
    prepare(ident, native_instructions([(3, 0x129, 100, 0), (0, 0, 0, 0)]), names=('F',))
    bound_f = emit('F', 1234); client.start(ident); consumed('F')
    detach('F'); replaced_f = attach('F')
    if replaced_f <= bound_f:
        raise AssertionError('Replacement did not advance F session')
    emit('F', 1234, pending=False); terminal(ident, 5, -116)
    # Retained START without reupload clears the old binding and reads normally.
    emit('F', 1234); client.start(ident); consumed('F')
    state = client.snapshot()
    if state is None or state['state'] != 2 or state['error']:
        raise AssertionError('Retained START failed to recover native reader')
    client.exchange(4, ident); terminal(ident, 4)
    # Caught ESTALE must remain sticky across three further embedded reads.
    ident = 0x3505
    prepare(ident, payload_bytes(sticky_python_source()), python=True, names=('F',))
    python_bound = emit('F', 1234); client.start(ident, allow_unwind=True); consumed('F')
    detach('F'); python_replacement = attach('F')
    if python_replacement <= python_bound:
        raise AssertionError('Python replacement did not advance F session')
    emit('F', 1234, pending=False); terminal(ident, 5, -116)
    ident = 0x3506
    prepare(ident, payload_bytes(python_reads_source(2222, 1234)), python=True)
    emit('E', 2222); emit('F', 1234)
    client.start(ident, allow_unwind=True); terminal(ident); consumed('E'); consumed('F')
    print('ARM explicit program sensor fixture passed: %r' % dict(
        firstE=first_e, firstF=first_f, nativeF=bound_f, replacedF=replaced_f,
        pythonF=python_bound, pythonReplacementF=python_replacement,
        externalReports=reports[0], requests=client.submissions, guestMs=elapsed[0],
        nativeCancellation=True, nativeRetainedRestart=True, caughtStaleReads=3,
        synchronizedNoData=True, wrongTypeRejected=True,
        nativeConditionalTrials=len(conditional_trials)))
