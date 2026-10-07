# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""External Classic jobs with observations of synthetic electrical motors.

No writes to guest memory, encoder positions or job completion are permitted.
The fixture only observes the existing public model and sets external load.
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
    if port not in ('A', 'B') or action not in ('state', 'load'):
        raise ValueError('Unsupported motor fixture action')
    motor = externals['port' + port].Device
    if motor is None:
        raise ValueError('Motor attachment unavailable')
    if action == 'load':
        if value not in (0, 100):
            raise ValueError('Unsupported motor fixture load')
        motor.SetLoad(value)
    receipt = json.dumps({'port': port, 'position': float(motor.PositionDegrees),
        'speed': float(motor.AngularVelocityDegreesPerSecond),
        'power': int(motor.Power), 'load': int(motor.LoadPercent),
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

    async def establish_encoder(self, port):
        # Advertising is not attachment readiness. The real API selects POS
        # asynchronously and reports EAGAIN until its UART frame arrives.
        # Every refused attempt is retained and must leave the motor unpowered.
        started = await self.model(port)
        for attempt in range(30):
            ident = 'w{}{:02d}'.format('AB'.index(port), attempt)
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


async def boundary_jobs(peer, record):
    for ident, overrides, error in [('p009', {'stop': 2}, -95),
                                    ('p010', {'speed': 0}, -22),
                                    ('p011', {'stall': True}, -95)]:
        params = {'port': 'A', 'speed': 30, 'degrees': 90, 'stop': 1, 'stall': False}
        params.update(overrides)
        peer.send(ident, 'scratch.motor_run_for_degrees', params)
        await peer.collect(ident, error)
        if (await peer.model('A'))['power'] != 0:
            raise AssertionError('Rejected request powered a motor')
        record['cases'].append({'case': ident, 'error': error})
    await peer.quiet(150)


async def motor_round_trip(dlc, received, renode, results, *, renode_log, case='all'):
    if case not in ('all', 'motion', 'cancel', 'no-progress'):
        raise ValueError('Unsupported motor scenario')
    record = results.setdefault('classic_motors', {'requests': [], 'replies': [],
                                                  'model_states': [], 'cases': [], 'selection': case})
    peer = MotorPeer(dlc, received, renode, renode_log, record)
    await peer.establish_encoder('A')
    if case in ('all', 'motion'):
        await peer.establish_encoder('B')
        await motion_jobs(peer, record)
    if case in ('all', 'cancel'):
        await cancellation_job(peer, record)
    if case in ('all', 'no-progress'):
        await no_progress_job(peer, record)
    await boundary_jobs(peer, record)
    record['passed'] = True
    record['exclusions'] = ['immediate back-to-back jobs', 'attachment loss/reconnect',
                            'disconnect ownership cleanup', 'counter wrap',
                            'timer-rearm failure', 'physical accuracy', 'HOLD']
