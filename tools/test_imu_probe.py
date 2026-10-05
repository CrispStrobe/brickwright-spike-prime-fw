#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Independent synthetic fixtures for the actual Classic acquisition parser."""
import asyncio
import importlib.util
import struct
import json
import shlex
import math
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'simulation/bluetooth-air/imu_probe.py'
spec = importlib.util.spec_from_file_location('imu_probe', SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def bundle(*, samples=((444,555,-666,111,222,-333,0),), sequence=1, stamp=123456):
    payload = b''.join(struct.pack('<hhhhhhI', *s) for s in samples)
    header = struct.pack('<HIHBBHBHB', sequence, stamp, len(payload), len(samples),
                         6, 833, 2, 1000, 1)
    tlvs = b''.join(struct.pack('<BBBBBBBBH', i,255,0,0,0,0,0,255,0) for i in range(6))
    frame = b'\x6b\xb6\x02\0\0'+header+payload+tlvs
    return frame[:3]+struct.pack('<H',len(frame))+frame[5:]


class FrameTests(unittest.TestCase):
    def test_real_layout_body_axes_config_and_stamp(self):
        data = probe.parse_bundle(bundle())
        sample = probe.validate_sample(data, (111,-222,333,444,-555,666))
        self.assertEqual(sample['timestamp_us'],123456)
        self.assertEqual(len(data['sensor_tlvs']),6)
        self.assertEqual(len(bytes.fromhex(data['frame_hex'])),97)

    def test_fragmented_coalesced_text_binary_and_partial(self):
        stream = b'OK\n'+bundle()+b'OK\n'+bundle(sequence=2)
        parser = probe.MixedFrames()
        events=[]
        for value in stream:
            events.extend(parser.feed(bytes([value])))
        parser.finish()
        self.assertEqual([e[0] for e in events], ['text','bundle','text','bundle'])
        parser=probe.MixedFrames()
        self.assertEqual(len(parser.feed(stream[:-3])),3)
        with self.assertRaisesRegex(ValueError,'Truncated'):
            parser.finish()
        self.assertEqual(len(parser.feed(stream[-3:])),1)
        parser.finish()

    def test_declared_length_header_count_and_trailing_rejected(self):
        changes=[(2,b'\x03'),(3,b'\0\0'),(11,b'\x20\0'),(13,b'\x09'),
                 (14,b'\x05'),(20,b'\x80')]
        for offset,data in changes:
            frame=bytearray(bundle());frame[offset:offset+len(data)]=data
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                probe.parse_bundle(bytes(frame))
        frame=bundle()+b'x';frame=frame[:3]+struct.pack('<H',len(frame))+frame[5:]
        with self.assertRaisesRegex(ValueError,'Trailing'):
            probe.parse_bundle(frame)

    def test_sensor_tlv_bounds_and_flags(self):
        for offset,value in [(37,2),(42,33),(43,4),(42,1)]:
            frame=bytearray(bundle());frame[offset]=value
            with self.subTest(offset=offset,value=value), self.assertRaises(ValueError):
                probe.parse_bundle(bytes(frame))
        frame=bytearray(bundle());frame[42]=32;frame[43]=2
        with self.assertRaises(ValueError):
            probe.parse_bundle(bytes(frame))

    def test_bad_timestamp_axes_configuration_and_extra_sample(self):
        with self.assertRaises(ValueError):
            probe.parse_bundle(bundle(samples=((1,2,3,4,5,6,1),)))
        for offset,data in [(15,b'\x68\0'),(17,b'\x08'),(18,b'\xd0\x07'),
                            (20,b'\0'),(21,b'\0\0')]:
            frame=bytearray(bundle());frame[offset:offset+len(data)]=data
            with self.subTest(offset=offset),self.assertRaises(ValueError):
                probe.validate_sample(probe.parse_bundle(bytes(frame)),(111,-222,333,444,-555,666))
        with self.assertRaises(ValueError):
            probe.validate_sample(probe.parse_bundle(bundle(stamp=0)),(111,-222,333,444,-555,666))
        with self.assertRaises(ValueError):
            probe.validate_sample(probe.parse_bundle(bundle(samples=((444,555,-666,111,222,-333,0),)*2)),(111,-222,333,444,-555,666))

    def test_buffer_text_envelope_and_burst_bounds(self):
        for data in [b'x'*4097,b'x'*257,b'\xff\n',b'x\x6b\xb6',
                     b'\x6b\xb6\x02\xff\xff',b'OK\n'*65]:
            with self.subTest(data=data[:10]),self.assertRaises(ValueError):
                probe.MixedFrames().feed(data)
        parser=probe.MixedFrames()
        self.assertEqual(parser.feed(b'\x6b'),[])
        with self.assertRaises(ValueError):parser.finish()

    def test_helper_is_python_and_copies_no_guest_write(self):
        compile(probe.RENODE_IMU_HELPER,'fixture.py','exec')
        self.assertNotIn('SetRegister',probe.RENODE_IMU_HELPER)
        self.assertNotIn('WriteDoubleWord',probe.RENODE_IMU_HELPER)
        self.assertIn('InjectSample',probe.RENODE_IMU_HELPER)


class ProbeLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, wrong_axes=False, deny=False, silent=False, cancel=False):
        received=asyncio.Queue()
        requests=[]
        started=asyncio.Event()
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'renode.log';log.write_text('')
            state={'on':False,'seq':0}
            class DLC:
                def write(self,data):
                    request=data.decode().strip();requests.append(request)
                    state['on']=request=='IMU ON'
                    received.put_nowait(b'OK\n')
            class Input:
                def write(self,data):
                    args=shlex.split(data.decode());action,tag=args[1:3]
                    started.set()
                    if silent:return
                    accepted=None
                    if action=='inject':
                        accepted=state['on'] and not deny
                    receipt={'accepted':accepted,'controls':[0x70,0x78] if state['on'] else [0,8], 'status':0}
                    with log.open('a') as output:
                        output.write('IMU_FIXTURE '+tag+' '+json.dumps(receipt)+'\n')
                    if accepted:
                        gx,gy,gz,ax,ay,az=map(int,args[3:])
                        sample=(ax,-ay,-az,gx,gy if wrong_axes else -gy,-gz,0)
                        state['seq']+=1
                        received.put_nowait(bundle(samples=(sample,),sequence=state['seq'],stamp=state['seq']*1000))
                async def drain(self):pass
            class Process:
                returncode=None
                stdin=Input()
            results={}
            task=asyncio.create_task(probe.imu_round_trip(DLC(),received,Process(),results,renode_log=log,timeout=0.05 if silent else 2))
            if cancel:
                await started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            elif silent:
                with self.assertRaises(TimeoutError):await task
            elif wrong_axes or deny:
                with self.assertRaises(ValueError):await task
            else:
                await task
            self.assertFalse(state['on'], 'Probe left streaming enabled')
            return results,requests

    async def test_actual_helper_on_off_on_flow(self):
        results,requests=await self.exercise()
        self.assertEqual(requests,['IMU ON','IMU OFF','IMU ON','IMU OFF'])
        self.assertEqual(results['imu_acquisition']['status'],'PASS')
        self.assertEqual(len(results['imu_acquisition']['samples']),3)
        self.assertIs(results['imu_acquisition']['model_receipts'][2]['accepted'],False)

    async def test_wrong_axes_and_denied_injection_fail_with_off_cleanup(self):
        for args in [{'wrong_axes':True},{'deny':True}]:
            results,requests=await self.exercise(**args)
            self.assertEqual(requests,['IMU ON','IMU OFF'])
            self.assertTrue(results['imu_acquisition']['status'].startswith('FAIL'))


    async def test_missing_receipt_timeout_and_cancellation_cleanup(self):
        for cancel in [False,True]:
            results,requests=await self.exercise(silent=True,cancel=cancel)
            self.assertEqual(requests,['IMU ON','IMU OFF'])
            self.assertTrue(results['imu_acquisition']['status'].startswith('FAIL'))


def fusion_line(sequence=1, stamp=1000, *, accel=(0, 0, 9806.65), gyro=(0, 0, 0), heading=0):
    angle = math.radians(heading)
    matrix = [math.cos(angle), math.sin(angle), 0, -math.sin(angle), math.cos(angle), 0, 0, 0, 1]
    values = [sequence, stamp, 0, 2, *accel, *gyro, heading, heading, *matrix]
    return 'FUSION SNAP ' + ' '.join(str(v) for v in values)


class FusionTests(unittest.TestCase):
    def test_layout_and_physical_units(self):
        snap = probe.parse_fusion(fusion_line())
        probe.validate_fusion(snap, (0, 0, 0, 0, 0, -16384))
        self.assertEqual(snap['orientation'], [1, 0, 0, 0, 1, 0, 0, 0, 1])
        parser = probe.MixedFrames()
        line = fusion_line().encode() + b'\n'
        events = []
        for byte in line:
            events += parser.feed(bytes([byte]))
        self.assertEqual(len(events), 1)
        parser.finish()

    def test_invalid_fields_and_matrix(self):
        for index, value in [(2, '0'), (3, str(2**64)), (4, '2'), (5, '3'),
                              (6, 'nan'), (8, 'inf'), (14, '2'), (22, '-1')]:
            words = fusion_line().split(); words[index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                probe.parse_fusion(' '.join(words))
        for line in [fusion_line()+' extra', fusion_line().replace('SNAP','OTHER'),
                     fusion_line().replace('SNAP ', 'SNAP  '), 'FUSION SNAP']:
            with self.assertRaises(ValueError): probe.parse_fusion(line)
        for kwargs in [{'accel': (0,0,9.80665)}, {'gyro': (0,0,1)}]:
            with self.assertRaises(ValueError):
                probe.validate_fusion(probe.parse_fusion(fusion_line(**kwargs)), (0,0,0,0,0,-16384))


class FusionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, wrong_units=False, deny=False, silent=False, cancel=False):
        received = asyncio.Queue(); requests = []; started = asyncio.Event()
        state = {'on': False, 'sequence': 0, 'time': 1000000, 'heading': 0,
                 'snapshot': None, 'odr': 833, 'accel': 2, 'gyro': 1000, 'changed': True}
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory)/'renode.log'; log.write_text('')
            class DLC:
                def write(self, data):
                    command = data.decode().strip(); requests.append(command)
                    if command == 'FUSION START':
                        state.update(on=True, sequence=0, heading=0, snapshot=None, changed=True)
                        reply = 'OK'
                    elif command == 'FUSION STOP':
                        state['on'] = False; reply = 'OK'
                    elif command == 'FUSION STATUS':
                        reply = 'FUSION STATUS 0 '+str(int(state['on']))+' 0'
                    elif command == 'FUSION GET':
                        reply = state['snapshot'] if state['on'] and state['snapshot'] and state['time']-state['stamp']<=300000 else 'ERR errno=11'
                    elif command.startswith('SET '):
                        _, field, value = command.split()
                        state[{'ODR':'odr', 'ACCEL_FSR':'accel', 'GYRO_FSR':'gyro'}[field]] = int(value)
                        state['changed'] = True; reply = 'OK'
                    else: raise AssertionError(command)
                    received.put_nowait((reply+'\n').encode())
            class Input:
                def write(self, data):
                    args = shlex.split(data.decode()); action, tag = args[1:3]
                    started.set()
                    if silent: return
                    state['time'] += 400000 if action == 'state' else 50000
                    accepted = state['on'] and not deny if action == 'inject' else None
                    if accepted:
                        gx,gy,gz,ax,ay,az = map(int, args[3:])
                        dt = 1/state['odr'] if state['changed'] else (state['time']-state['stamp'])/1000000
                        state['heading'] -= -gz*state['gyro']*.035/1000*dt
                        state['changed'] = False
                        state['stamp'] = state['time']; state['sequence'] += 1
                        accel = tuple(v*state['accel']*9806.65/32768 for v in (ax,-ay,-az))
                        if wrong_units: accel = tuple(v/1000 for v in accel)
                        gyro = tuple(v*state['gyro']*.035/1000 for v in (gx,-gy,-gz))
                        state['snapshot'] = fusion_line(state['sequence'],state['stamp'],accel=accel,gyro=gyro,heading=state['heading'])
                    receipt = {'accepted':accepted,'controls':[0x70,0x78] if state['on'] else [0,8], 'status':0, 'virtual_us':state['time']}
                    with log.open('a') as out: out.write('IMU_FIXTURE '+tag+' '+json.dumps(receipt)+'\n')
                async def drain(self): pass
            class Process:
                returncode = None
                stdin = Input()
            result = {}
            task = asyncio.create_task(probe.fusion_round_trip(DLC(),received,Process(),result,renode_log=log,timeout=.05 if silent else 3))
            if cancel:
                await started.wait(); task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
            elif silent:
                with self.assertRaises(TimeoutError): await task
            elif wrong_units or deny:
                with self.assertRaises(ValueError): await task
            else: await task
            self.assertFalse(state['on'], 'Fusion probe left producer enabled')
            return result, requests

    async def test_guest_contract_flow(self):
        result, requests = await self.exercise()
        self.assertEqual(result['imu_fusion']['status'], 'PASS')
        self.assertEqual(len(result['imu_fusion']['snapshots']), 4)
        self.assertTrue(result['imu_fusion']['stale_rejected'])
        self.assertEqual(requests.count('FUSION START'), 2)
        self.assertEqual(requests.count('FUSION STOP'), 2)

    async def test_failures_timeout_and_cancel_stop(self):
        for kwargs in [{'wrong_units':True}, {'deny':True}, {'silent':True}, {'silent':True,'cancel':True}]:
            with self.subTest(kwargs=kwargs):
                result, requests = await self.exercise(**kwargs)
                self.assertTrue(result['imu_fusion']['status'].startswith('FAIL'))
                self.assertEqual(requests[-1], 'FUSION STOP')



class StationaryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, wrong_ready=False, unlearned_bias=False,
                       skipped_feed=False, silent=False, cancel=False,
                       persistence=False, lost_saved_bias=False, save_error=False):
        received = asyncio.Queue(); requests = []; actions = []
        started = asyncio.Event()
        state = {'on': False, 'sequence': 0, 'time': 1000000,
                 'stamp': 0, 'feed': [0, 104, 0, 0, 0, 0], 'odr': 833,
                 'saved': False, 'loaded_bias': False}
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'renode.log'; log.write_text('')
            class DLC:
                def write(self, data):
                    command = data.decode().strip(); requests.append(command)
                    if command == 'FUSION START':
                        state.update(on=True, sequence=0, stamp=0,
                                     loaded_bias=state.get('saved', False) and not lost_saved_bias)
                        reply = 'OK'
                    elif command == 'FUSION CAL SAVE':
                        if save_error:
                            reply = 'ERR errno=28'
                        else:
                            state['saved'] = state['sequence'] >= 437
                            reply = 'OK'
                    elif command == 'FUSION CAL LOAD':
                        reply = 'OK' if state['saved'] else 'ERR errno=2'
                    elif command == 'FUSION STOP':
                        state['on'] = False; reply = 'OK'
                    elif command == 'FUSION STATUS':
                        reply = 'FUSION STATUS 0 '+str(int(state['on']))+' 0'
                    elif command == 'FUSION GET':
                        if not state['on'] or not state['sequence']:
                            reply = 'ERR errno=11'
                        else:
                            calibrated = state['sequence'] >= 229
                            gyro = (0, 0, 0) if (calibrated or state['loaded_bias']) and not unlearned_bias else (.7, 1.05, 1.4)
                            words = fusion_line(state['sequence'], state['stamp'], gyro=gyro).split()
                            words[4] = str(int(calibrated and not wrong_ready))
                            reply = ' '.join(words)
                    elif command.startswith('SET '):
                        _, field, value = command.split()
                        if field == 'ODR': state['odr'] = int(value)
                        reply = 'OK'
                    else:
                        raise AssertionError(command)
                    # Deliberately fragment the response at an arbitrary boundary.
                    encoded = (reply+'\n').encode()
                    received.put_nowait(encoded[:7]); received.put_nowait(encoded[7:])
            class Input:
                def write(self, data):
                    args = shlex.split(data.decode()); action, tag = args[1:3]
                    actions.append(action)
                    if action == 'inject':
                        if not cancel: started.set()
                        if silent and not cancel: return
                        state['time'] += 10000
                        state['sequence'] += 1; state['stamp'] = state['time']
                        accepted = state['on']
                    elif action == 'feed':
                        ticks = int(args[-1])
                        state['time'] += math.ceil(ticks * 1000000 / state['odr'])
                        state['sequence'] += ticks; state['stamp'] = state['time']
                        state['feed'] = [0, state['odr'], ticks,
                                         ticks - int(skipped_feed), int(skipped_feed), 0]
                        accepted = state['on']
                        if cancel:
                            state['feed'][0] = 1
                            started.set()
                            return
                    elif action == 'feed_stop':
                        state['feed'][0] = 0; accepted = None
                    elif action == 'state': accepted = None
                    else: raise AssertionError(action)
                    # The feed admission receipt marks the beginning of its
                    # configured guest-time interval; state marks completion.
                    virtual_us = state['time']
                    if action == 'feed':
                        virtual_us -= math.ceil(ticks * 1000000 / state['odr'])
                    receipt = {'accepted': accepted,
                               'controls': [0x50, 0x58] if state['on'] else [0, 8],
                               'status': 0, 'virtual_us': virtual_us,
                               'feed': state['feed']}
                    with log.open('a') as out:
                        out.write('IMU_FIXTURE '+tag+' '+json.dumps(receipt)+'\n')
                async def drain(self): pass
            class Process:
                returncode = None
                stdin = Input()
            result = {}
            task = asyncio.create_task(probe.stationary_round_trip(
                DLC(), received, Process(), result, renode_log=log,
                timeout=.05 if silent else 3, persistence=persistence))
            if cancel:
                await started.wait(); task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
            elif silent:
                with self.assertRaises(TimeoutError): await task
            elif wrong_ready or unlearned_bias or skipped_feed or lost_saved_bias or save_error:
                with self.assertRaises(ValueError): await task
            else: await task
            self.assertFalse(state['on'], 'Stationary probe left producer enabled')
            self.assertFalse(state['feed'][0], 'Stationary probe left feeder enabled')
            self.assertEqual(actions[-1], 'feed_stop')
            return result, requests, actions

    async def test_guest_calibration_save_reopen_bias_without_readiness(self):
        result, requests, actions = await self.exercise(persistence=True)
        record = result['imu_calibration']
        self.assertEqual(record['status'], 'PASS')
        self.assertTrue(record['loaded_bias_verified'])
        self.assertFalse(record['physical_durability_qualified'])
        self.assertEqual(record['saved_sequence'], 441)
        self.assertEqual([s['sequence'] for s in record['snapshots']], [1, 101, 261, 441, 1])
        self.assertIn('FUSION CAL SAVE', requests)
        self.assertIn('FUSION CAL LOAD', requests)
        self.assertFalse(record['snapshots'][-1]['ready'])

    async def test_guest_calibration_lost_bias_is_rejected(self):
        result, _, _ = await self.exercise(persistence=True, lost_saved_bias=True)
        self.assertTrue(result['imu_calibration']['status'].startswith('FAIL'))
        self.assertNotIn('loaded_bias_verified', result['imu_calibration'])

    async def test_guest_calibration_save_error_is_rejected(self):
        result, _, _ = await self.exercise(persistence=True, save_error=True)
        self.assertTrue(result['imu_calibration']['status'].startswith('FAIL'))
        self.assertNotIn('loaded_bias_verified', result['imu_calibration'])

    async def test_configured_rate_ready_bias_and_reopen(self):
        result, requests, actions = await self.exercise()
        record = result['imu_stationary']
        self.assertEqual(record['status'], 'PASS')
        self.assertEqual([s['sequence'] for s in record['snapshots']], [1, 101, 261, 1])
        self.assertEqual([s['ready'] for s in record['snapshots']], [False, False, True, False])
        self.assertEqual(requests.count('FUSION START'), 2)
        self.assertEqual(requests.count('FUSION STOP'), 2)
        self.assertEqual(requests[-1], 'SET ODR 833')
        self.assertEqual(actions.count('feed'), 2)

    async def test_wrong_readiness_bias_and_skipped_feed_stop(self):
        for kwargs in [{'wrong_ready': True}, {'unlearned_bias': True},
                       {'skipped_feed': True}]:
            with self.subTest(kwargs=kwargs):
                result, requests, _ = await self.exercise(**kwargs)
                self.assertTrue(result['imu_stationary']['status'].startswith('FAIL'))
                self.assertEqual(requests[-1], 'FUSION STOP')

    async def test_missing_receipt_and_cancellation_cleanup(self):
        for cancel in [False, True]:
            with self.subTest(cancel=cancel):
                result, requests, _ = await self.exercise(silent=True, cancel=cancel)
                self.assertTrue(result['imu_stationary']['status'].startswith('FAIL'))
                self.assertEqual(requests[-1], 'FUSION STOP')


class PoseLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, wrong_face=False, wrong_base=False,
                       mutated_matrix=False, invalid_mutation=False,
                       silent=False, cancel=False):
        received = asyncio.Queue(); requests = []; started = asyncio.Event()
        state = {'on': False, 'stamp': 1000000, 'snapshot': None, 'base': False}
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'renode.log'; log.write_text('')

            def reply_snapshot():
                physical = state['snapshot']
                accel, gyro = physical['accel'], physical['gyro']
                matrix = physical['matrix'][:]
                heading = physical['heading']
                if state['base']:
                    project = lambda v: (v[1], v[0] if wrong_base else -v[0], v[2])
                    accel, gyro = project(accel), project(gyro)
                    heading = 0
                    if mutated_matrix:
                        # Rotate two matrix rows while retaining a proper
                        # orthonormal rotation, so the parser alone accepts it.
                        matrix = matrix[3:6] + [-v for v in matrix[:3]] + matrix[6:]
                values = [1, state['stamp'], 0, physical['face'], *accel, *gyro,
                          heading, heading, *matrix]
                return 'FUSION SNAP ' + ' '.join(str(v) for v in values)

            class DLC:
                def write(self, data):
                    command = data.decode().strip(); requests.append(command)
                    if command == 'FUSION START':
                        state.update(on=True, snapshot=None, base=False)
                        reply = 'OK'
                    elif command == 'FUSION STOP':
                        state['on'] = False; reply = 'OK'
                    elif command == 'FUSION STATUS':
                        reply = 'FUSION STATUS 0 '+str(int(state['on']))+' 0'
                    elif command == 'FUSION GET':
                        reply = reply_snapshot() if state['on'] and state['snapshot'] else 'ERR errno=11'
                    elif command == 'FUSION BASE 1 0 0 1 0 0':
                        if invalid_mutation: state['snapshot']['gyro'] = (1, 2, 3)
                        reply = 'ERR invalid FUSION BASE'
                    elif command.startswith('FUSION BASE '):
                        if not state['on']: reply = 'ERR errno=11'
                        else:
                            state['base'] = command == 'FUSION BASE 0 1 0 0 0 1'
                            reply = 'OK'
                    elif command.startswith('SET '): reply = 'OK'
                    else: raise AssertionError(command)
                    encoded = (reply+'\n').encode()
                    received.put_nowait(encoded[:9]); received.put_nowait(encoded[9:])

            class Input:
                def write(self, data):
                    args = shlex.split(data.decode()); action, tag = args[1:3]
                    accepted = None
                    if action == 'inject':
                        started.set()
                        if silent: return
                        gx, gy, gz, ax, ay, az = map(int, args[3:])
                        accel = tuple(v * 9806.65 / 16384 for v in (ax, -ay, -az))
                        gravity = tuple(v / 9806.65 for v in accel)
                        row1 = (0, 1, 0) if gravity[0] else (1, 0, 0)
                        # row2 = gravity cross row1 gives determinant +1.
                        row2 = (gravity[1]*row1[2]-gravity[2]*row1[1],
                                gravity[2]*row1[0]-gravity[0]*row1[2],
                                gravity[0]*row1[1]-gravity[1]*row1[0])
                        face = {(0, 0, -16384): 2, (16384, 0, 0): 0,
                                (0, 16384, 0): 5, (0, 0, 16384): 6,
                                (-16384, 0, 0): 4, (0, -16384, 0): 1}[(ax, ay, az)]
                        state['stamp'] += 10000
                        state['snapshot'] = {
                            'accel': accel, 'gyro': (gx*.035, -gy*.035, -gz*.035),
                            'matrix': [*row1, *row2, *gravity],
                            'face': 6 if wrong_face else face,
                            'heading': .2 if gx or gy or gz else 0}
                        accepted = state['on']
                    elif action != 'state': raise AssertionError(action)
                    receipt = {'accepted': accepted,
                               'controls': [0x70, 0x78] if state['on'] else [0, 8],
                               'status': 0, 'virtual_us': state['stamp']}
                    with log.open('a') as out:
                        out.write('IMU_FIXTURE '+tag+' '+json.dumps(receipt)+'\n')
                async def drain(self): pass

            class Process:
                returncode = None
                stdin = Input()
            result = {}
            task = asyncio.create_task(probe.pose_round_trip(
                DLC(), received, Process(), result, renode_log=log,
                timeout=.05 if silent else 3))
            if cancel:
                await started.wait(); task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
            elif silent:
                with self.assertRaises(TimeoutError): await task
            elif wrong_face or wrong_base or mutated_matrix or invalid_mutation:
                with self.assertRaises(ValueError): await task
            else: await task
            self.assertFalse(state['on'], 'Pose probe left producer enabled')
            return result, requests

    async def test_six_faces_base_projection_identity_and_stop(self):
        result, requests = await self.exercise()
        record = result['imu_poses']
        self.assertEqual(record['status'], 'PASS')
        self.assertEqual([item['pose'] for item in record['snapshots']],
                         ['top', 'front', 'right', 'bottom', 'back', 'left', 'gyro'])
        self.assertEqual([item['physical']['up_side'] for item in record['snapshots']],
                         [2, 0, 5, 6, 4, 1, 2])
        self.assertEqual(requests.count('FUSION START'), 7)
        self.assertEqual(requests.count('FUSION STOP'), 7)
        for actual, wanted in zip(record['snapshots'][-1]['mapped']['gyro_dps'], (1.05, -.7, 1.4)):
            self.assertAlmostEqual(actual, wanted)

    async def test_wrong_face_base_sign_matrix_and_invalid_mutation_cleanup(self):
        for kwargs in [{'wrong_face': True}, {'wrong_base': True},
                       {'mutated_matrix': True}, {'invalid_mutation': True}]:
            with self.subTest(kwargs=kwargs):
                result, requests = await self.exercise(**kwargs)
                self.assertTrue(result['imu_poses']['status'].startswith('FAIL'))
                self.assertEqual(requests[-1], 'FUSION STOP')

    async def test_missing_receipt_and_cancellation_cleanup(self):
        for cancel in [False, True]:
            with self.subTest(cancel=cancel):
                result, requests = await self.exercise(silent=True, cancel=cancel)
                self.assertTrue(result['imu_poses']['status'].startswith('FAIL'))
                self.assertEqual(requests[-1], 'FUSION STOP')


if __name__=='__main__':unittest.main()
