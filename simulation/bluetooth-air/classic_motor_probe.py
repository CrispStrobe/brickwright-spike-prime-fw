# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""External Classic jobs with observations of synthetic electrical motors.

No writes to guest memory, encoder positions or job completion are permitted.
The fixture observes the public model and sets external load/attachment inputs.
Optional DCM observations read our own kernel using hash-bound debug metadata.
"""
import asyncio
import json
import math
import uuid
from collections import deque

from imu_probe import MixedFrames


RENODE_MOTOR_HELPER = r'''# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
import json
def mc_classic_motor(action, port, tag, value=0):
    if port not in ('A', 'B') or action not in ('state', 'load', 'detach', 'attach'):
        raise ValueError('Unsupported motor fixture action')
    attachment = externals['port' + port]
    if action == 'detach': attachment.Detach()
    if action == 'attach': attachment.Attach('motor')
    motor = attachment.Device
    if action == 'load':
        if motor is None or value not in (0, 100):
            raise ValueError('Unsupported motor fixture load')
        motor.SetLoad(value)
    guest = None
    layout = globals().get('_classic_port_layout')
    if layout:
        bus = monitor.Machine['sysbus']
        base = layout['address'] + 'ABCDEF'.index(port) * layout['stride']
        offsets = layout['offsets']
        for attempt in range(3):
            first = bus.ReadDoubleWord(base + offsets['event_counter'])
            kind = bus.ReadByte(base + offsets['confirmed_type'])
            flags = bus.ReadByte(base + offsets['flags'])
            last = bus.ReadDoubleWord(base + offsets['event_counter'])
            if first == last:
                guest = dict(event_counter=int(last), confirmed_type=int(kind), flags=int(flags))
                break
        if guest is None: raise ValueError('DCM observation changed during sampling')
    receipt = json.dumps({'port': port, 'position': float(motor.PositionDegrees) if motor else None,
        'speed': float(motor.AngularVelocityDegreesPerSecond) if motor else None,
        'power': int(motor.Power) if motor else None, 'load': int(motor.LoadPercent) if motor else None,
        'attached': motor is not None, 'generation': int(attachment.TopologyGeneration),
        'bridge_drive': int(attachment.BridgeDrive) if hasattr(attachment, 'BridgeDrive') else None,
        'bridge_braking': bool(attachment.BridgeBraking) if hasattr(attachment, 'BridgeBraking') else None,
        'guest': guest,
        'virtual_us': int(monitor.Machine.ElapsedVirtualTime.TimeElapsed.TotalMicroseconds)}, sort_keys=True)
    monitor.Parse('log "CLASSIC_MOTOR ' + tag + ' ' + receipt.replace('"', '\\"') + '"')
'''


def require_move(before, after, degrees, *, tolerance=20):
    """Check actual signed displacement and released drive, independently of RPC."""
    delta = after['position'] - before['position']
    signed = delta if degrees > 0 else -delta
    if not math.isfinite(delta) or not abs(degrees) - 1 <= signed <= abs(degrees) + tolerance:
        raise AssertionError('Measured displacement outside job contract: ' + str(delta))
    if after['power'] != 0:
        raise AssertionError('Completed job retained powered drive')
    if after['virtual_us'] <= before['virtual_us']:
        raise AssertionError('Guest time did not advance')
    return delta


def require_reply(reply, request_id, error=0):
    expected = {'i': request_id, 'r': None} if not error else {'i': request_id, 'e': {'code': error}}
    if reply != expected:
        raise AssertionError('Unexpected Classic job result: ' + repr(reply))


def require_disconnect(before, detached, after):
    guest = after['guest']
    elapsed = after['virtual_us'] - detached['virtual_us']
    if (not guest or guest['confirmed_type'] != 0 or guest['flags'] & 1
            or guest['event_counter'] == before['guest']['event_counter']
            or after['bridge_drive'] != 0 or not 0 < elapsed <= 2500000):
        raise AssertionError('Guest disconnect did not advance identity and release the bridge within its bound')
    return elapsed


class MotorPeer:
    def __init__(self, dlc, received, renode, log, record):
        self.dlc, self.received, self.renode, self.log = dlc, received, renode, log
        self.record = record
        self.parser = MixedFrames()
        self.events = deque()
        self.replies = {}
        self.sent = set()

    def send(self, ident, method, params):
        if ident in self.sent:
            raise ValueError('Request id reused')
        self.sent.add(ident)
        request = {'i': ident, 'm': method, 'p': params}
        self.record['requests'].append(request)
        self.dlc.write((json.dumps(request, separators=(',', ':')) + '\r').encode('ascii'))

    def degrees(self, ident, port, angle):
        self.send(ident, 'scratch.motor_run_for_degrees',
                  {'port': port, 'speed': 30, 'degrees': angle, 'stop': 1, 'stall': False})

    async def collect(self, ident, error=0):
        async with asyncio.timeout(120):
            while ident not in self.replies:
                if not self.events:
                    self.events.extend(self.parser.feed(await self.received.get()))
                while self.events:
                    kind, value = self.events.popleft()
                    if kind != 'text' or not value.startswith('{'):
                        continue
                    reply = json.loads(value)
                    key = reply.get('i')
                    if key not in self.sent or key in self.replies:
                        raise AssertionError('Unknown or duplicate Classic reply: ' + value)
                    self.replies[key] = reply
                    self.record['replies'].append(reply)
        if error is not None:
            require_reply(self.replies[ident], ident, error)
        return self.replies[ident]

    async def model(self, port, action='state', value=0):
        tag = uuid.uuid4().hex
        marker = ('CLASSIC_MOTOR ' + tag + ' ').encode('ascii')
        offset = self.log.stat().st_size
        if self.renode.stdin is None or self.renode.returncode is not None:
            raise ValueError('Owned Renode monitor unavailable')
        command = 'classic_motor "{}" "{}" "{}" {}\n'.format(action, port, tag, value)
        self.renode.stdin.write(command.encode('ascii'))
        await self.renode.stdin.drain()
        async with asyncio.timeout(30):
            while True:
                if self.renode.returncode is not None:
                    raise ValueError('Renode exited during motor observation')
                with self.log.open('rb') as stream:
                    stream.seek(offset)
                    raw = stream.read(65536)
                if marker in raw:
                    tail = raw.split(marker, 1)[1]
                    if b'\n' in tail:
                        state, _ = json.JSONDecoder().raw_decode(tail.decode('ascii'))
                        self.record['model_states'].append({'action': action, **state})
                        return state
                if len(raw) == 65536:
                    raise ValueError('Motor receipt exceeds log bound')
                await asyncio.sleep(.05)

    async def moving(self, *ports):
        async with asyncio.timeout(60):
            while True:
                states = [await self.model(port) for port in ports]
                if all(abs(state['speed']) > 1 and state['power'] != 0 for state in states):
                    return states
                await asyncio.sleep(.1)

    async def wait_virtual(self, milliseconds):
        before = await self.model('A')
        async with asyncio.timeout(120):
            while (await self.model('A'))['virtual_us'] - before['virtual_us'] < milliseconds * 1000:
                await asyncio.sleep(.25)

    async def establish_encoder(self, port, tag='w'):
        # Advertising is not attachment readiness. The real API selects POS
        # asynchronously and reports EAGAIN until its UART frame arrives.
        # Every refused attempt is retained and must leave the motor unpowered.
        started = await self.model(port)
        for attempt in range(30):
            ident = '{}{}{:02d}'.format(tag, 'AB'.index(port), attempt)
            before = await self.model(port)
            if before['virtual_us'] - started['virtual_us'] > 3000000:
                raise AssertionError('Motor encoder did not become ready within 3 guest seconds')
            self.degrees(ident, port, 30)
            reply = await self.collect(ident, None)
            error = reply.get('e', {}).get('code', 0)
            after = await self.model(port)
            if error in (-11, -19):
                require_reply(reply, ident, error)
                if after['power'] != 0:
                    raise AssertionError('Not-ready request powered the motor')
                await self.wait_virtual(100)
                continue
            require_reply(reply, ident)
            self.record['cases'].append({'case': 'encoder-ready-' + port,
                                        'delta': require_move(before, after, 30)})
            await self.quiet(150)
            return
        raise AssertionError('Motor encoder readiness attempt bound reached')

    async def quiet(self, milliseconds=100):
        start = await self.model('A')
        async with asyncio.timeout(60):
            while True:
                try:
                    self.events.extend(self.parser.feed(await asyncio.wait_for(self.received.get(), .1)))
                except asyncio.TimeoutError:
                    pass
                for kind, value in self.events:
                    if kind == 'text' and value.startswith('{'):
                        raise AssertionError('Late or duplicate job reply: ' + value)
                self.events.clear()
                state = await self.model('A')
                if state['virtual_us'] - start['virtual_us'] >= milliseconds * 1000:
                    return


async def motion_jobs(peer, record):
    # Positive and negative encoder-coupled jobs, with independent observations.
    for ident, angle in [('p001', 90), ('p002', -90)]:
        before = await peer.model('A')
        peer.degrees(ident, 'A', angle)
        await peer.collect(ident)
        after = await peer.model('A')
        record['cases'].append({'case': ident, 'delta': require_move(before, after, angle)})
        await peer.quiet(150)
    before = [await peer.model(port) for port in 'AB']
    peer.degrees('p003', 'A', 180)
    peer.degrees('p004', 'B', -180)
    await peer.moving('A', 'B')
    await peer.collect('p003'); await peer.collect('p004')
    for index, (port, angle) in enumerate([('A', 180), ('B', -180)]):
        after = await peer.model(port)
        record['cases'].append({'case': 'concurrent-' + port,
                                'delta': require_move(before[index], after, angle)})


async def cancellation_job(peer, record):
    peer.degrees('p005', 'A', 10000)
    await peer.moving('A')
    peer.send('p006', 'scratch.motor_stop', {'port': 'A', 'stop': 1})
    await peer.collect('p005'); await peer.collect('p006')
    # Let brake settle before measuring a new signed baseline.
    await peer.quiet(150)
    before = await peer.model('A')
    peer.degrees('p007', 'A', -180)
    await peer.moving('A'); await peer.collect('p007')
    after = await peer.model('A')
    record['cases'].append({'case': 'cancel-replace', 'delta': require_move(before, after, -180)})
    await peer.quiet(150)


async def no_progress_job(peer, record):
    before = await peer.model('A', 'load', 100)
    peer.degrees('p008', 'A', 90)
    await peer.collect('p008', -110)
    after = await peer.model('A')
    if abs(after['position'] - before['position']) > 1 or after['power'] != 0:
        raise AssertionError('No-progress job moved or retained power')
    if after['virtual_us'] - before['virtual_us'] < 1000000:
        raise AssertionError('No-progress error arrived before guest timeout')
    record['cases'].append({'case': 'no-progress', 'error': -110,
                            'elapsed_us': after['virtual_us'] - before['virtual_us']})
    await peer.model('A', 'load', 0)
    await peer.quiet(150)


# Pinned NuttX include/errno.h: ENOTSUP=138; EOPNOTSUPP=95 is distinct.
NUTTX_ENOTSUP = 138


async def boundary_jobs(peer, record):
    for ident, overrides, error in [('p009', {'stop': 2}, -NUTTX_ENOTSUP),
                                    ('p010', {'speed': 0}, -22),
                                    ('p011', {'stall': True}, -NUTTX_ENOTSUP)]:
        params = {'port': 'A', 'speed': 30, 'degrees': 90, 'stop': 1, 'stall': False}
        params.update(overrides)
        peer.send(ident, 'scratch.motor_run_for_degrees', params)
        await peer.collect(ident, error)
        if (await peer.model('A'))['power'] != 0:
            raise AssertionError('Rejected request powered a motor')
        record['cases'].append({'case': ident, 'error': error})
    await peer.quiet(150)


async def detach_job(peer, record):
    peer.degrees('d001', 'A', 10000)
    before = (await peer.moving('A'))[0]
    if not before['guest'] or before['bridge_drive'] == 0:
        raise AssertionError('Detach requires actual guest identity and powered bridge observations')
    detached = await peer.model('A', 'detach')
    if detached['attached'] or detached['bridge_drive'] == 0:
        raise AssertionError('Model detach hid the guest bridge demand')
    reply = await peer.collect('d001', None)
    error = reply.get('e', {}).get('code')
    if error not in (-19, -116, -110):
        raise AssertionError('Detached job did not report a supported explicit failure: ' + repr(reply))
    # Observe natural guest execution; never force DCM state or the clock.
    async with asyncio.timeout(120):
        while True:
            state = await peer.model('A')
            if state['guest']['confirmed_type'] == 0 and state['guest']['event_counter'] != before['guest']['event_counter']:
                break
            if state['virtual_us'] - detached['virtual_us'] > 2500000:
                raise AssertionError('Guest DCM did not confirm disconnect within 2.5 simulated seconds')
            await asyncio.sleep(.1)
    disconnect_us = require_disconnect(before, detached, state)
    peer.degrees('d002', 'A', 30)
    await peer.collect('d002', -19)
    if (await peer.model('A'))['bridge_drive'] != 0:
        raise AssertionError('Disconnected request powered the bridge')
    replacement = await peer.model('A', 'attach')
    if replacement['generation'] != detached['generation'] + 1 or replacement['position'] != 0 or replacement['power'] != 0:
        raise AssertionError('Replacement inherited mechanics or powered demand')
    await peer.establish_encoder('A', tag='r')
    fresh = await peer.model('A')
    if fresh['guest']['event_counter'] == state['guest']['event_counter'] or not fresh['guest']['flags'] & 1:
        raise AssertionError('Guest did not discover a fresh attachment')
    peer.degrees('d003', 'A', -90)
    await peer.moving('A');await peer.collect('d003')
    after = await peer.model('A')
    if after['bridge_drive'] != 0:
        raise AssertionError('Replacement completed with bridge demand still active')
    record['cases'].append({'case': 'detach-reconnect', 'error': error,
        'disconnect_guest_us': disconnect_us,
        'before_guest': before['guest'], 'disconnected_guest': state['guest'],
        'replacement_guest': after['guest'], 'released_bridge': state['bridge_drive'],
        'delta': require_move(fresh, after, -90)})
    await peer.quiet(150)


async def motor_round_trip(dlc, received, renode, results, *, renode_log, case='all'):
    if case not in ('all', 'motion', 'cancel', 'no-progress', 'detach'):
        raise ValueError('Unsupported motor scenario')
    record = results.setdefault('classic_motors', {'requests': [], 'replies': [],
                                                  'model_states': [], 'cases': [], 'selection': case})
    peer = MotorPeer(dlc, received, renode, renode_log, record)
    await peer.establish_encoder('A')
    if case == 'detach':
        await detach_job(peer, record)
    if case in ('all', 'motion'):
        await peer.establish_encoder('B')
        await motion_jobs(peer, record)
    if case in ('all', 'cancel'):
        await cancellation_job(peer, record)
    if case in ('all', 'no-progress'):
        await no_progress_job(peer, record)
    await boundary_jobs(peer, record)
    record['passed'] = True
    record['exclusions'] = ['immediate back-to-back jobs',
                            'transport-disconnect ownership cleanup', 'counter wrap',
                            'timer-rearm failure', 'physical accuracy', 'HOLD']
    if case != 'detach':
        record['exclusions'].append('attachment loss/reconnect')
    else:
        record['exclusions'].append('arbitrary hotplug interleavings')
