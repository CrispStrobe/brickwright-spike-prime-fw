#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Independent synthetic fixtures for the actual Classic acquisition parser."""
import asyncio
import importlib.util
import struct
import json
import shlex
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


if __name__=='__main__':unittest.main()

