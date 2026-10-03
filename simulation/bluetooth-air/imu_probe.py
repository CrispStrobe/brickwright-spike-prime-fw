# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Synthetic IMU inputs observed through the actual guest Classic BUNDLE path.

The local BUNDLE format has no checksum, temperature or per-sample FSR indices.
These checks cover framing, raw body axes, timestamps and header configuration;
physical units, autonomous ODR timing and fusion are outside this qualification.
"""
import asyncio
import json
import struct
import uuid
from collections import deque
from pathlib import Path

MAGIC = b"\x6b\xb6"
MAX_FRAME = 401  # own btsensor_wire.h: 5+16+8*16+6*(10+32)
MAX_BUFFER = 4096

RENODE_IMU_HELPER = '''# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
import json
def mc_imu_fixture(action, tag, gx=0, gy=0, gz=0, ax=0, ay=0, az=0):
    imu = monitor.Machine['sysbus.i2c2.imu']
    if action not in ('state', 'inject'):
        raise ValueError('Unsupported IMU fixture action')
    accepted = None
    if action == 'inject':
        accepted = bool(imu.InjectSample(gx, gy, gz, ax, ay, az))
    state = [int(value) for value in imu.GetFixtureState()]
    controls = state[:2]
    status = int(state[2])
    receipt = json.dumps({'accepted': accepted, 'controls': controls,
                          'status': status}, sort_keys=True)
    monitor.Parse('log "IMU_FIXTURE ' + tag + ' ' + receipt.replace('"', '\\\\"') + '"')
'''


def parse_bundle(frame: bytes) -> dict:
    if len(frame) < 81 or len(frame) > MAX_FRAME or frame[:3] != MAGIC + b"\x02":
        raise ValueError("Invalid BUNDLE envelope")
    if struct.unpack_from("<H", frame, 3)[0] != len(frame):
        raise ValueError("BUNDLE length mismatch")
    seq, tick, section, count, tlv_count, rate, accel, gyro, flags = struct.unpack_from(
        "<HIHBBHBHB", frame, 5)
    if count > 8 or section != count * 16 or tlv_count != 6 or flags & ~3:
        raise ValueError("Invalid BUNDLE header")
    offset = 21
    samples = []
    for index in range(count):
        if offset + 16 > len(frame):
            raise ValueError("Truncated IMU slot")
        ax, ay, az, gx, gy, gz, delta = struct.unpack_from("<hhhhhhI", frame, offset)
        if (index == 0 and delta != 0) or delta >= 0x80000000:
            raise ValueError("Invalid IMU timestamp delta")
        if samples and delta < samples[-1]["delta_us"]:
            raise ValueError("IMU timestamps are unordered")
        samples.append({"accel": [ax, ay, az], "gyro": [gx, gy, gz],
                        "delta_us": delta, "timestamp_us": (tick + delta) & 0xffffffff})
        offset += 16
    tlvs = []
    for index in range(6):
        if offset + 10 > len(frame):
            raise ValueError("Truncated sensor TLV")
        cls, port, mode, dtype, values, length, tf, age, t_seq = struct.unpack_from(
            "<BBBBBBBBH", frame, offset)
        if cls != index or length > 32 or tf & ~3 or (length and not tf & 2):
            raise ValueError("Invalid sensor TLV")
        offset += 10
        if offset + length > len(frame):
            raise ValueError("Truncated sensor payload")
        tlvs.append({"class_id": cls, "payload_hex": frame[offset:offset+length].hex()})
        offset += length
    if offset != len(frame):
        raise ValueError("Trailing bytes in BUNDLE")
    return {"sequence": seq, "tick_timestamp_us": tick, "sample_rate_hz": rate,
            "accel_fsr_g": accel, "gyro_fsr_dps": gyro, "flags": flags,
            "samples": samples, "sensor_tlvs": tlvs, "frame_hex": frame.hex()}


class MixedFrames:
    """Bounded RFCOMM text lines and raw binary BUNDLE, without resync guesses."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list:
        self.buffer.extend(data)
        if len(self.buffer) > MAX_BUFFER:
            raise ValueError("RFCOMM buffer exceeds bound")
        events = []
        while self.buffer:
            if self.buffer[:2] == MAGIC:
                if len(self.buffer) < 5:
                    break
                length = struct.unpack_from("<H", self.buffer, 3)[0]
                if length < 81 or length > MAX_FRAME:
                    raise ValueError("Invalid advertised BUNDLE length")
                if len(self.buffer) < length:
                    break
                frame = bytes(self.buffer[:length])
                del self.buffer[:length]
                events.append(("bundle", parse_bundle(frame)))
            else:
                # A partial magic prefix is not an unfinished text line.
                if self.buffer == MAGIC[:1]:
                    break
                newline = self.buffer.find(b"\n")
                magic = self.buffer.find(MAGIC)
                if magic >= 0 and (newline < 0 or magic < newline):
                    raise ValueError("Unterminated text before binary frame")
                if newline < 0:
                    if len(self.buffer) > 256:
                        raise ValueError("RFCOMM text line exceeds bound")
                    break
                if newline > 256:
                    raise ValueError("RFCOMM text line exceeds bound")
                line = bytes(self.buffer[:newline]).rstrip(b"\r")
                del self.buffer[:newline+1]
                try:
                    text = line.decode("ascii")
                except UnicodeDecodeError as error:
                    raise ValueError("Invalid RFCOMM text") from error
                if any(ord(c) < 32 or ord(c) > 126 for c in text):
                    raise ValueError("Control character in RFCOMM text")
                events.append(("text", text))
            if len(events) > 64:
                raise ValueError("RFCOMM event burst exceeds bound")
        return events

    def finish(self):
        if self.buffer:
            raise ValueError("Truncated RFCOMM stream")


def validate_sample(bundle: dict, expected: tuple[int, ...]) -> dict | None:
    """Require guest chip-to-body Y/Z negation and actual default config."""
    gx, gy, gz, ax, ay, az = expected
    if len(bundle["samples"]) > 1:
        raise ValueError("Unexpected extra synthetic IMU sample")
    for sample in bundle["samples"]:
        if sample["gyro"] != [gx, -gy, -gz] or sample["accel"] != [ax, -ay, -az]:
            raise ValueError("Guest IMU raw body axes differ from synthetic input")
        if (bundle["sample_rate_hz"], bundle["accel_fsr_g"], bundle["gyro_fsr_dps"]) != (833, 2, 1000):
            raise ValueError("Guest IMU rate/FSR header differs")
        if not bundle["flags"] & 1 or sample["timestamp_us"] == 0:
            raise ValueError("Guest IMU sample lacks active flag/timestamp")
        return sample
    return None


async def imu_round_trip(dlc, received, renode_proc, results: dict, *,
                         renode_log: Path, timeout: float = 120) -> None:
    parser = MixedFrames()
    pending = deque()
    record = results.setdefault("imu_acquisition", {"samples": [], "commands": [],
                                                   "model_receipts": []})

    async def next_event():
        while not pending:
            pending.extend(parser.feed(await received.get()))
        kind, value = pending.popleft()
        if kind == "text" and value.startswith("ERR"):
            raise ValueError("Guest rejected IMU request: " + value)
        return kind, value

    async def command(state):
        request = "IMU " + state
        dlc.write((request + "\n").encode("ascii"))
        async with asyncio.timeout(20):
            skipped = 0
            while True:
                kind, value = await next_event()
                if kind == "text" and value == "OK":
                    record["commands"].append({"request": request, "reply": value})
                    return
                skipped += 1
                if skipped > 256:
                    raise ValueError("Too many events before IMU acknowledgement")

    async def model(action, values=()):
        if renode_proc.stdin is None or renode_proc.returncode is not None:
            raise ValueError("Renode monitor input unavailable")
        tag = uuid.uuid4().hex
        mark = "IMU_FIXTURE " + tag + " "
        offset = renode_log.stat().st_size
        cmd = 'imu_fixture "' + action + '" "' + tag + '"'
        if values:
            cmd += " " + " ".join(str(v) for v in values)
        renode_proc.stdin.write((cmd + "\n").encode("ascii"))
        await renode_proc.stdin.drain()
        async with asyncio.timeout(20):
            while True:
                if renode_proc.returncode is not None:
                    raise ValueError("Renode exited during IMU fixture")
                with renode_log.open("rb") as log:
                    log.seek(offset)
                    raw = log.read(65536)
                if mark.encode() in raw:
                    tail = raw.split(mark.encode(), 1)[1]
                    if b"\n" in tail:
                        # Logger suffixes/terminal coloring follow the JSON.
                        value, _ = json.JSONDecoder().raw_decode(tail.decode("ascii"))
                        record["model_receipts"].append({"action": action, **value})
                        return value
                if len(raw) == 65536:
                    raise ValueError("IMU monitor receipt exceeds log bound")
                await asyncio.sleep(0.05)

    async def sample(values):
        value = await model("inject", values)
        if value["accepted"] is not True:
            raise ValueError("Powered guest did not accept synthetic IMU sample")
        async with asyncio.timeout(30):
            while True:
                kind, bundle = await next_event()
                if kind != "bundle":
                    raise ValueError("Unexpected text while awaiting IMU sample")
                found = validate_sample(bundle, values)
                if found is None:
                    record["empty_bundles"] = record.get("empty_bundles", 0) + 1
                    record["last_empty_bundle"] = bundle
                if found:
                    if record["samples"]:
                        prior = record["samples"][-1]
                        delta = (found["timestamp_us"] - prior["sample"]["timestamp_us"]) & 0xffffffff
                        seq_delta = (bundle["sequence"] - prior["bundle"]["sequence"]) & 0xffff
                        if not 0 < delta < 0x80000000 or not 0 < seq_delta < 0x8000:
                            raise ValueError("IMU timestamp/sequence did not advance")
                    record["samples"].append({"input_gyro_accel": list(values),
                                               "sample": found, "bundle": bundle})
                    return

    active = False
    try:
        async with asyncio.timeout(timeout):
            await command("ON")
            active = True
            await sample((111, -222, 333, 444, -555, 666))
            await sample((-711, 822, -933, 1044, 1155, -1266))
            await command("OFF")
            active = False
            disabled = await model("inject", (1, 2, 3, 4, 5, 6))
            if disabled["accepted"] is not False or any(v >> 4 for v in disabled["controls"]):
                raise ValueError("IMU OFF did not power down both sensor ODRs")
            await command("ON")
            active = True
            await sample((1311, -1422, 1533, -1644, 1755, 1866))
            await command("OFF")
            active = False
            state = await model("state")
            if any(v >> 4 for v in state["controls"]):
                raise ValueError("Final IMU OFF did not power down")
            record["status"] = "PASS"
    except BaseException as error:
        record["status"] = "FAIL: " + type(error).__name__ + ": " + str(error)
        if isinstance(error, TimeoutError):
            try:
                async with asyncio.timeout(2):
                    record["timeout_model_state"] = await model("state")
            except BaseException:
                pass
        raise
    finally:
        if active:
            # Caller disconnects the peer as well; preserve the original error.
            try:
                await command("OFF")
            except BaseException:
                pass
