#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Christian Strobele
"""Decode bounded, user-declared IMU captures without inferring wire mappings.

This reads complete SPIKE COBS frames from JSONL. It neither communicates with
hardware nor authenticates the claimed capture source or firmware provenance.
"""
import argparse
import json
import re
import struct
import sys
from collections import Counter

from spike_codec import cobs_decode

MAX_INPUT = 8 * 1024 * 1024
MAX_LINE = 8 * 1024
MAX_FRAMES = 1200
MAX_FRAME_BYTES = 1200
MAX_PAYLOAD = 1024
MAX_RECORDS = 10000
RECORD_LENGTHS = {0: 2, 1: 21, 2: 26, 10: 12, 11: 4, 12: 9, 13: 4, 14: 11}
HEX = re.compile(r"[0-9a-fA-F]+\Z")


def _integer(value):
    return type(value) is int


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite JSON number")


def _metadata(value):
    required = {"schema", "kind", "declared_source", "firmware_version"}
    if (not isinstance(value, dict) or not required <= value.keys() or
            value.keys() - required - {"firmware_image_sha256"}):
        raise ValueError("invalid metadata fields")
    if (not _integer(value["schema"]) or value["schema"] != 1 or
            value["kind"] != "metadata" or
            value["declared_source"] not in ("reference", "synthetic")):
        raise ValueError("unsupported capture metadata")
    version = value["firmware_version"]
    if not isinstance(version, str) or not version.strip() or len(version) > 128:
        raise ValueError("invalid firmware version")
    digest = value.get("firmware_image_sha256")
    if digest is not None and (not isinstance(digest, str) or len(digest) != 64 or
                               HEX.fullmatch(digest) is None):
        raise ValueError("invalid firmware image SHA-256")
    return {**value, "firmware_image_sha256": digest,
            "provenance_verified": False,
            "provenance_note": "Source and firmware provenance are user-declared."}


def decode_notification(frame):
    """Validate the entire notification before returning any decoded records."""
    if len(frame) > MAX_FRAME_BYTES:
        raise ValueError("encoded frame exceeds byte bound")
    message = cobs_decode(frame)
    if len(message) < 3 or message[0] != 0x3C:
        raise ValueError("not a DeviceNotification envelope")
    length = struct.unpack_from("<H", message, 1)[0]
    if len(message) > MAX_PAYLOAD or len(message) != length + 3:
        raise ValueError("notification payload length differs or exceeds bound")
    records = []
    offset = 3
    while offset < len(message):
        kind = message[offset]
        size = RECORD_LENGTHS.get(kind)
        if size is None:
            raise ValueError("unknown device record type")
        if offset + size > len(message):
            raise ValueError("truncated device record")
        raw = message[offset:offset + size]
        record = {"type": kind, "raw_hex": raw.hex()}
        if kind == 0 and raw[1] > 100:
            raise ValueError("battery percentage exceeds 100")
        if kind == 1:
            if raw[1] > 5 or raw[2] > 5:
                raise ValueError("invalid physical or yaw face")
            values = struct.unpack_from("<9h", raw, 3)
            record.update(face_up=raw[1], yaw_face=raw[2],
                          yaw_raw=values[0], pitch_raw=values[1], roll_raw=values[2],
                          accel_raw=list(values[3:6]), gyro_raw=list(values[6:9]))
        records.append(record)
        offset += size
    return records


def read_capture(stream):
    """Read a binary stream atomically; return only a fully validated report."""
    total = 0
    metadata = None
    notifications = []
    counts = Counter()
    experiment_counts = {}
    record_count = imu_count = 0
    previous_timestamp = -1
    while True:
        raw = stream.readline(MAX_LINE + 1)
        if not raw:
            break
        total += len(raw)
        if total > MAX_INPUT:
            raise ValueError("capture exceeds input byte bound")
        if len(raw) > MAX_LINE:
            raise ValueError("capture line exceeds byte bound")
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                               parse_constant=_constant)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("invalid capture JSONL") from error
        if metadata is None:
            metadata = _metadata(value)
            continue
        if not isinstance(value, dict) or value.keys() != {
                "kind", "experiment", "timestamp_us", "frame_hex"} or value["kind"] != "notification":
            raise ValueError("invalid notification fields")
        label = value["experiment"]
        if (not isinstance(label, str) or not label.strip() or len(label) > 128 or
                any(ord(char) < 32 or ord(char) == 127 for char in label)):
            raise ValueError("invalid experiment label")
        timestamp = value["timestamp_us"]
        if not _integer(timestamp) or timestamp < 0 or timestamp <= previous_timestamp:
            raise ValueError("notification timestamps must strictly increase")
        previous_timestamp = timestamp
        encoded = value["frame_hex"]
        if (not isinstance(encoded, str) or len(encoded) % 2 or not encoded or
                HEX.fullmatch(encoded) is None):
            raise ValueError("invalid complete frame hex")
        if len(encoded) > MAX_FRAME_BYTES * 2:
            raise ValueError("encoded frame exceeds byte bound")
        if len(notifications) >= MAX_FRAMES:
            raise ValueError("capture frame count exceeds bound")
        records = decode_notification(bytes.fromhex(encoded))
        record_count += len(records)
        if record_count > MAX_RECORDS:
            raise ValueError("capture record count exceeds bound")
        current_imu = sum(record["type"] == 1 for record in records)
        imu_count += current_imu
        counts[label] += 1
        grouped = experiment_counts.setdefault(label, {"frame_count": 0,
            "record_count": 0, "imu_record_count": 0})
        grouped["frame_count"] += 1
        grouped["record_count"] += len(records)
        grouped["imu_record_count"] += current_imu
        notifications.append({"experiment": label, "timestamp_us": timestamp,
                              "records": records})
    if metadata is None or imu_count == 0:
        raise ValueError("capture requires metadata and at least one IMU record")
    return {"schema": 1, "metadata": metadata, "wire_mapping_qualified": False,
            "frame_count": len(notifications), "record_count": record_count,
            "imu_record_count": imu_count, "frames_by_experiment": dict(counts),
            "counts_by_experiment": experiment_counts,
            "notifications": notifications}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="read-only JSONL capture file")
    args = parser.parse_args(argv)
    try:
        with open(args.capture, "rb") as stream:
            report = read_capture(stream)
    except (OSError, ValueError) as error:
        print("imu_reference: " + str(error), file=sys.stderr)
        return 1
    json.dump(report, sys.stdout, sort_keys=True, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
