#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Christian Strobele
"""Independent raw-field golden and hostile-capture decoder checks."""
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'simulation/bluetooth-air/imu_reference.py'
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location('imu_reference', SOURCE)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
from spike_codec import cobs_encode

# Fixed complete frame: type60,length23,battery100,IMUface0/yawface5,
# nine signed words (-32768,32767,0,-1,1,-300,300,-2,32767).
GOLDEN = '063f14005b670007060583fc7c005afcfc0059d7fd2f04fdfcfc7c02'
META = {'schema': 1, 'kind': 'metadata', 'declared_source': 'reference',
        'firmware_version': 'example-unverified-version',
        'firmware_image_sha256': 'a' * 64}
FRAME = {'kind': 'notification', 'experiment': 'signed-boundaries',
         'timestamp_us': 0, 'frame_hex': GOLDEN}


def stream(*values):
    return io.BytesIO(('\n'.join(json.dumps(v) for v in values)+'\n').encode())


def envelope(records):
    return cobs_encode(b'\x3c'+struct.pack('<H', len(records))+records)


class ReferenceTests(unittest.TestCase):
    def test_independent_signed_golden(self):
        report = reference.read_capture(stream(META, FRAME))
        self.assertEqual(report['frame_count'], 1)
        self.assertEqual(report['record_count'], 2)
        self.assertEqual(report['imu_record_count'], 1)
        self.assertEqual(report['frames_by_experiment'], {'signed-boundaries': 1})
        self.assertEqual(report['counts_by_experiment'], {'signed-boundaries':
                         {'frame_count': 1, 'record_count': 2, 'imu_record_count': 1}})
        records = report['notifications'][0]['records']
        self.assertEqual(records[0], {'type': 0, 'raw_hex': '0064'})
        imu = records[1]
        self.assertEqual((imu['face_up'], imu['yaw_face']), (0, 5))
        self.assertEqual((imu['yaw_raw'], imu['pitch_raw'], imu['roll_raw']),
                         (-32768, 32767, 0))
        self.assertEqual(imu['accel_raw'], [-1, 1, -300])
        self.assertEqual(imu['gyro_raw'], [300, -2, 32767])
        self.assertEqual(bytes.fromhex(imu['raw_hex'])[0], 1)

    def test_declared_sources_never_qualify_mapping_or_provenance(self):
        for source in ['reference', 'synthetic']:
            metadata = {**META, 'declared_source': source}
            report = reference.read_capture(stream(metadata, FRAME))
            self.assertIs(report['wire_mapping_qualified'], False)
            self.assertIs(report['metadata']['provenance_verified'], False)
            self.assertEqual(report['metadata']['declared_source'], source)
        for digest in [None, 'ABCDEF' * 10 + 'ABCD']:
            self.assertEqual(reference.read_capture(stream(
                {**META, 'firmware_image_sha256': digest}, FRAME))['metadata']['firmware_image_sha256'], digest)
        minimal = dict(META); del minimal['firmware_image_sha256']
        self.assertIsNone(reference.read_capture(stream(minimal, FRAME))['metadata']['firmware_image_sha256'])

    def test_all_other_known_records_preserved_and_experiments_grouped(self):
        raw = b''.join(bytes([kind])+bytes(size-1)
                       for kind, size in reference.RECORD_LENGTHS.items() if kind != 1)
        second = {**FRAME, 'timestamp_us': 1, 'frame_hex': envelope(raw).hex()}
        third = {**FRAME, 'experiment': 'other', 'timestamp_us': 2}
        report = reference.read_capture(stream(META, FRAME, second, third))
        self.assertEqual(report['frames_by_experiment'], {'signed-boundaries': 2, 'other': 1})
        others = report['notifications'][1]['records']
        self.assertEqual([r['type'] for r in others], [0, 2, 10, 11, 12, 13, 14])
        self.assertTrue(all(set(r) == {'type', 'raw_hex'} for r in others))
        self.assertEqual(b''.join(bytes.fromhex(r['raw_hex']) for r in others), raw)

    def test_unknown_truncated_faces_battery_and_envelope_rejected_atomically(self):
        imu = bytes.fromhex('0100050080ff7f0000ffff0100d4fe2c01feffff7f')
        invalid = [imu+b'\xff', b'\x00\x65'+imu,
                   bytes([1, 6])+imu[2:], imu[:2]+bytes([6])+imu[3:]]
        invalid += [bytes([kind])+bytes(size-2)
                    for kind, size in reference.RECORD_LENGTHS.items()]
        for raw in invalid:
            with self.subTest(raw=raw.hex()), self.assertRaises(ValueError):
                reference.decode_notification(envelope(raw))
        for message in [b'\x3c', b'\x3c\x01\x00', b'\x3c\x00\x00\x00', b'\x32\x00\x00']:
            with self.subTest(message=message.hex()), self.assertRaises(ValueError):
                reference.decode_notification(cobs_encode(message))

    def test_complete_frame_required_not_fragments_or_aggregated_frames(self):
        golden = bytes.fromhex(GOLDEN)
        self.assertEqual(reference.decode_notification(b'\x01'+golden),
                         reference.decode_notification(golden))
        for frame in [b'', golden[:-1], golden[:5], golden+golden,
                      golden+b'x', b'\x01\x02', b'\x03\x02', b'\x04\x02']:
            with self.subTest(frame=frame.hex()), self.assertRaises(ValueError):
                reference.decode_notification(frame)

    def test_metadata_and_notification_validation(self):
        metadata_changes = {'schema': [True, 2], 'kind': ['notification'],
                            'declared_source': ['trusted', None],
                            'firmware_version': ['', None, 'x'*129],
                            'firmware_image_sha256': ['a'*63, 'z'*64, 123]}
        for field, values in metadata_changes.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    reference.read_capture(stream({**META, field: value}, FRAME))
        frame_changes = {'kind': ['metadata'], 'timestamp_us': [True, -1, 1.5],
                         'experiment': ['', 'x'*129, 'bad\nlabel'],
                         'frame_hex': ['', 'abc', 'ab xx', None]}
        for field, values in frame_changes.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    reference.read_capture(stream(META, {**FRAME, field: value}))
        for values in [(), (FRAME,), (META,), (META, META), (META, FRAME, FRAME),
                       (META, {**FRAME, 'timestamp_us': 2}, {**FRAME, 'timestamp_us': 1})]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                reference.read_capture(stream(*values))
        for raw in [b'{}\n', b'\xff\n', b'\n',
                    b'{"schema":1,"schema":1}\n', b'{"schema":NaN}\n']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                reference.read_capture(io.BytesIO(raw))
        battery_only = {**FRAME, 'frame_hex': envelope(b'\x00\x64').hex()}
        with self.assertRaisesRegex(ValueError, 'at least one IMU'):
            reference.read_capture(stream(META, battery_only))

    def test_resource_bounds(self):
        data = stream(META, FRAME).getvalue()
        with patch.object(reference, 'MAX_INPUT', len(data)-1), self.assertRaisesRegex(ValueError, 'input byte'):
            reference.read_capture(io.BytesIO(data))
        with self.assertRaisesRegex(ValueError, 'line'):
            reference.read_capture(io.BytesIO(b'x'*(reference.MAX_LINE+1)))
        records = b'\x00\x64' * 511
        with self.assertRaisesRegex(ValueError, 'payload'):
            reference.decode_notification(envelope(records))
        with self.assertRaisesRegex(ValueError, 'encoded frame'):
            reference.decode_notification(b'x' * (reference.MAX_FRAME_BYTES + 1))
        oversized = {**FRAME, 'frame_hex': 'ff' * (reference.MAX_FRAME_BYTES + 1)}
        with self.assertRaisesRegex(ValueError, 'encoded frame'):
            reference.read_capture(stream(META, oversized))
        # Full message length is bounded including the three-byte envelope.
        within_bound = envelope(b'\x00\x64' * 510)
        self.assertEqual(len(reference.decode_notification(within_bound)), 510)
        frames = [{**FRAME, 'timestamp_us': i} for i in range(reference.MAX_FRAMES+1)]
        with self.assertRaisesRegex(ValueError, 'frame count'):
            reference.read_capture(stream(META, *frames))
        many = envelope(b'\x00\x64'*500).hex()
        frames = [FRAME]+[{**FRAME, 'timestamp_us': i+1, 'frame_hex': many} for i in range(20)]
        with self.assertRaisesRegex(ValueError, 'record count'):
            reference.read_capture(stream(META, *frames))

    def test_cli_valid_report_and_invalid_file_no_partial_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'capture.jsonl'
            good = stream(META, FRAME).getvalue(); path.write_bytes(good)
            result = subprocess.run([sys.executable, str(SOURCE), str(path)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['wire_mapping_qualified'])
            self.assertEqual(path.read_bytes(), good)
            bad = good + json.dumps({**FRAME, 'timestamp_us': 1, 'frame_hex': '0402'}).encode()+b'\n'
            path.write_bytes(bad)
            result = subprocess.run([sys.executable, str(SOURCE), str(path)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'')
            self.assertIn(b'imu_reference:', result.stderr)
            self.assertEqual(path.read_bytes(), bad)


if __name__ == '__main__':
    unittest.main()
