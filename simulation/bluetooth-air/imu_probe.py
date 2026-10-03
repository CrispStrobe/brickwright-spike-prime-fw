# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Synthetic IMU inputs observed through the actual guest Classic BUNDLE path.

The local BUNDLE format has no checksum, temperature or per-sample FSR indices.
These checks cover framing, raw body axes, timestamps and header configuration;
the separate fusion probe checks timestamped physical-unit snapshots through
the actual producer. Autonomous ODR timing and physical accuracy remain outside
this synthetic qualification.
"""
import asyncio
import json
import math
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
def mc_imu_fixture(action, tag, gx=0, gy=0, gz=0, ax=0, ay=0, az=0, ticks=0):
    imu = monitor.Machine['sysbus.i2c2.imu']
    if action not in ('state', 'inject', 'feed', 'feed_stop'):
        raise ValueError('Unsupported IMU fixture action')
    accepted = None
    if action == 'inject':
        accepted = bool(imu.InjectSample(gx, gy, gz, ax, ay, az))
    if action == 'feed':
        accepted = bool(imu.StartFixtureFeed(gx, gy, gz, ax, ay, az, ticks))
    if action == 'feed_stop':
        imu.StopFixtureFeed()
    state = [int(value) for value in imu.GetFixtureState()]
    controls = state[:2]
    status = int(state[2])
    virtual_us = int(monitor.Machine.ElapsedVirtualTime.TimeElapsed.TotalMicroseconds)
    receipt = json.dumps({'accepted': accepted, 'controls': controls,
                          'status': status, 'virtual_us': virtual_us,
                          'feed': [int(value) for value in imu.GetFixtureFeedState()]}, sort_keys=True)
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


def parse_fusion(line: str) -> dict:
    """Strict local physical-unit snapshot, distinct from modern IMU records."""
    tokens = line.split(" ")
    if len(tokens) != 23 or tokens[:2] != ["FUSION", "SNAP"]:
        raise ValueError("Invalid fusion snapshot layout")
    integers = tokens[2:6]
    if any(not s.isascii() or not s.isdecimal() for s in integers):
        raise ValueError("Invalid fusion integer")
    sequence, timestamp, ready, side = map(int, integers)
    if not 0 < sequence < 2**64 or not 0 < timestamp < 2**64 or ready not in (0, 1) or side not in (0, 1, 2, 4, 5, 6):
        raise ValueError("Invalid fusion metadata")
    values = list(map(float, tokens[6:]))
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Nonfinite fusion value")
    matrix = values[8:]
    for row in range(3):
        for other in range(3):
            dot = sum(matrix[row*3+i] * matrix[other*3+i] for i in range(3))
            if abs(dot - (1 if row == other else 0)) > .001:
                raise ValueError("Fusion orientation is not orthonormal")
    determinant = (matrix[0]*(matrix[4]*matrix[8]-matrix[5]*matrix[7]) -
                   matrix[1]*(matrix[3]*matrix[8]-matrix[5]*matrix[6]) +
                   matrix[2]*(matrix[3]*matrix[7]-matrix[4]*matrix[6]))
    if abs(determinant - 1) > .001:
        raise ValueError("Fusion orientation is not a proper rotation")
    return {"sequence": sequence, "timestamp_us": timestamp, "ready": bool(ready),
            "up_side": side, "accel_mms2": values[:3], "gyro_dps": values[3:6],
            "heading_1d_deg": values[6], "heading_3d_deg": values[7],
            "orientation": matrix, "line": line}


def validate_fusion(snapshot: dict, fixture: tuple, *, accel_g=2, gyro_dps=1000):
    gx, gy, gz, ax, ay, az = fixture
    expected_accel = [ax, -ay, -az]
    expected_gyro = [gx, -gy, -gz]
    for actual, raw in zip(snapshot["accel_mms2"], expected_accel):
        if not math.isclose(actual, raw * accel_g * 9806.65 / 32768, abs_tol=.1):
            raise ValueError("Fusion acceleration units/axes differ")
    for actual, raw in zip(snapshot["gyro_dps"], expected_gyro):
        if not math.isclose(actual, raw * gyro_dps * .035 / 1000, abs_tol=.001):
            raise ValueError("Fusion gyro units/axes differ")
    if snapshot["ready"] or snapshot["up_side"] != 2:
        raise ValueError("Sparse upright fixture incorrectly reports readiness/face")


async def fusion_round_trip(dlc, received, renode_proc, results: dict, *,
                            renode_log: Path, timeout: float = 120) -> None:
    parser = MixedFrames()
    pending = deque()
    record = results.setdefault("imu_fusion", {"snapshots": [], "commands": [],
                                               "model_receipts": []})

    async def request(command):
        dlc.write((command + "\n").encode("ascii"))
        async with asyncio.timeout(20):
            for _ in range(256):
                while not pending:
                    pending.extend(parser.feed(await received.get()))
                kind, value = pending.popleft()
                if kind == "bundle":
                    if value["samples"]:
                        raise ValueError("Raw samples arrived during fusion-only probe")
                    continue
                record["commands"].append({"request": command, "reply": value})
                return value
            raise ValueError("Too many events before fusion reply")

    async def ok(command):
        value = await request(command)
        if value != "OK":
            raise ValueError("Guest rejected fusion control: " + value)

    async def state(running):
        async with asyncio.timeout(20):
            while True:
                value = await request("FUSION STATUS")
                if value == ("FUSION STATUS 0 1 0" if running else "FUSION STATUS 0 0 0"):
                    return
                if value not in ("FUSION STATUS 1 0 0", "FUSION STATUS 0 1 1", "FUSION STATUS 1 0 1"):
                    raise ValueError("Invalid fusion lifecycle status: " + value)
                await asyncio.sleep(.05)

    async def model(action, values=()):
        if renode_proc.stdin is None or renode_proc.returncode is not None:
            raise ValueError("Renode monitor input unavailable")
        tag = uuid.uuid4().hex
        marker = ("IMU_FIXTURE " + tag + " ").encode()
        offset = renode_log.stat().st_size
        command = 'imu_fixture "' + action + '" "' + tag + '"'
        if values:
            command += " " + " ".join(str(v) for v in values)
        renode_proc.stdin.write((command + "\n").encode())
        await renode_proc.stdin.drain()
        async with asyncio.timeout(20):
            while True:
                if renode_proc.returncode is not None:
                    raise ValueError("Renode exited during fusion fixture")
                with renode_log.open("rb") as log:
                    log.seek(offset)
                    raw = log.read(65536)
                if marker in raw and b"\n" in raw.split(marker, 1)[1]:
                    value, _ = json.JSONDecoder().raw_decode(raw.split(marker, 1)[1].decode())
                    record["model_receipts"].append({"action": action, **value})
                    return value
                if len(raw) == 65536:
                    raise ValueError("Fusion monitor receipt exceeds log bound")
                await asyncio.sleep(.05)

    async def snapshot(fixture, *, accel_g=2, gyro_dps=1000, previous=None):
        if (await model("inject", fixture))["accepted"] is not True:
            raise ValueError("Fusion producer did not power sensor")
        async with asyncio.timeout(30):
            while True:
                line = await request("FUSION GET")
                if line == "ERR errno=11":
                    await asyncio.sleep(.01)
                    continue
                snap = parse_fusion(line)
                if previous and snap["sequence"] == previous["sequence"]:
                    await asyncio.sleep(.01)
                    continue
                validate_fusion(snap, fixture, accel_g=accel_g, gyro_dps=gyro_dps)
                if previous and (snap["sequence"] <= previous["sequence"] or snap["timestamp_us"] <= previous["timestamp_us"]):
                    raise ValueError("Fusion source sequence/time did not advance")
                record["snapshots"].append({"fixture": list(fixture), **snap})
                return snap

    active = False
    try:
        async with asyncio.timeout(timeout):
            await state(False)
            if await request("FUSION GET") != "ERR errno=11":
                raise ValueError("Stopped fusion returned a snapshot")
            active = True  # Cleanup even when an acknowledgement is lost.
            await ok("FUSION START")
            await state(True)
            first = await snapshot((0, 0, 0, 0, 0, -16384))
            if await request("FUSION GET") != first["line"]:
                raise ValueError("Fusion snapshot read consumed/changed publication")
            second = await snapshot((0, 0, -1000, 0, 0, -16384), previous=first)
            expected_heading = -35 * (second["timestamp_us"] - first["timestamp_us"]) / 1000000
            if not math.isclose(second["heading_1d_deg"], expected_heading, abs_tol=.002):
                raise ValueError("Fusion heading did not integrate source timestamp delta")
            if abs(second["orientation"][1]) < 1e-6:
                raise ValueError("Fusion orientation missed current integration step")
            await ok("SET ODR 52")
            await ok("SET ACCEL_FSR 4")
            await ok("SET GYRO_FSR 500")
            third = await snapshot((0, 0, -1000, 0, 0, -8192), accel_g=4, gyro_dps=500, previous=second)
            if not math.isclose(third["heading_1d_deg"] - second["heading_1d_deg"], -17.5/52, abs_tol=.002):
                raise ValueError("Fusion configuration restart did not use new nominal ODR")
            # Freshness is measured in virtual time, not assumed from host sleep.
            clock = await model("state")
            # This is a guest-time expiration test. The diagnostic emulator
            # advances about 5 ms of guest time per host second; keep the
            # overall 120 s probe limit and ordinary request budgets unchanged.
            async with asyncio.timeout(90):
                while (await model("state"))["virtual_us"] - clock["virtual_us"] <= 310000:
                    await asyncio.sleep(1)
            if await request("FUSION GET") != "ERR errno=11":
                raise ValueError("Stale fusion snapshot remained available")
            record["stale_rejected"] = True
            await ok("FUSION STOP")
            if await request("FUSION GET") != "ERR errno=11":
                raise ValueError("Stopping fusion returned a snapshot")
            await state(False)
            disabled = await model("inject", (1, 2, 3, 4, 5, 6))
            if disabled["accepted"] is not False or any(v >> 4 for v in disabled["controls"]):
                raise ValueError("Fusion STOP did not release sensor subscription")
            await ok("SET ODR 833")
            await ok("SET ACCEL_FSR 2")
            await ok("SET GYRO_FSR 1000")
            await ok("FUSION START")
            await state(True)
            reopened = await snapshot((0, 0, 0, 0, 0, -16384))
            if reopened["sequence"] != 1 or reopened["timestamp_us"] <= third["timestamp_us"]:
                raise ValueError("Reopened fusion did not publish a fresh initial snapshot")
            await ok("FUSION STOP")
            await state(False)
            active = False
            if any(v >> 4 for v in (await model("state"))["controls"]):
                raise ValueError("Final fusion STOP did not power down")
            record["status"] = "PASS"
    except BaseException as error:
        record["status"] = "FAIL: " + type(error).__name__ + ": " + str(error)
        raise
    finally:
        if active:
            try:
                await ok("FUSION STOP")
            except BaseException:
                pass


async def stationary_round_trip(dlc, received, renode_proc, results: dict, *,
                                renode_log: Path, timeout: float = 900) -> None:
    """Configured-rate synthetic stationarity; no firmware/clock substitution.

    The first window qualifies readiness and live bias correction. This does
    not assert durable calibration, physical motion or autonomous silicon ODR.
    """
    parser = MixedFrames()
    pending = deque()
    fixture = (20, -30, -40, 0, 0, -16384)
    record = results.setdefault("imu_stationary", {"snapshots": [], "commands": [],
                                                  "model_receipts": []})

    async def request(command):
        dlc.write((command + "\n").encode("ascii"))
        async with asyncio.timeout(20):
            for _ in range(256):
                while not pending:
                    pending.extend(parser.feed(await received.get()))
                kind, value = pending.popleft()
                if kind == "bundle":
                    if value["samples"]:
                        raise ValueError("Raw samples arrived during stationary probe")
                    continue
                record["commands"].append({"request": command, "reply": value})
                return value
            raise ValueError("Too many events before stationary reply")

    async def ok(command):
        if await request(command) != "OK":
            raise ValueError("Guest rejected stationary control: " + command)

    async def running(wanted):
        async with asyncio.timeout(20):
            while True:
                value = await request("FUSION STATUS")
                if value == ("FUSION STATUS 0 1 0" if wanted else "FUSION STATUS 0 0 0"):
                    return
                if value not in ("FUSION STATUS 1 0 0", "FUSION STATUS 0 1 1", "FUSION STATUS 1 0 1"):
                    raise ValueError("Invalid stationary lifecycle status")
                await asyncio.sleep(.05)

    async def model(action, values=()):
        if renode_proc.stdin is None or renode_proc.returncode is not None:
            raise ValueError("Renode monitor input unavailable")
        tag = uuid.uuid4().hex
        marker = ("IMU_FIXTURE " + tag + " ").encode()
        offset = renode_log.stat().st_size
        command = 'imu_fixture "' + action + '" "' + tag + '"'
        if values:
            command += " " + " ".join(str(v) for v in values)
        renode_proc.stdin.write((command + "\n").encode())
        await renode_proc.stdin.drain()
        async with asyncio.timeout(20):
            while True:
                if renode_proc.returncode is not None:
                    raise ValueError("Renode exited during stationary fixture")
                with renode_log.open("rb") as log:
                    log.seek(offset)
                    raw = log.read(65536)
                if marker in raw and b"\n" in raw.split(marker, 1)[1]:
                    value, _ = json.JSONDecoder().raw_decode(raw.split(marker, 1)[1].decode())
                    record["model_receipts"].append({"action": action, **value})
                    return value
                if len(raw) == 65536:
                    raise ValueError("Stationary receipt exceeds log bound")
                await asyncio.sleep(.05)

    async def snapshot(sequence):
        async with asyncio.timeout(30):
            while True:
                line = await request("FUSION GET")
                if line == "ERR errno=11":
                    await asyncio.sleep(.05)
                    continue
                snap = parse_fusion(line)
                if snap["sequence"] < sequence:
                    await asyncio.sleep(.05)
                    continue
                if snap["sequence"] != sequence:
                    raise ValueError("Stationary producer lost/added samples")
                record["snapshots"].append(snap)
                return snap

    async def feed(ticks):
        initial = await model("feed", (*fixture, ticks))
        if initial["accepted"] is not True:
            raise ValueError("Stationary fixture feed was not admitted")
        while True:
            receipt = await model("state")
            active, rate, attempts, accepted, skipped, remaining = receipt["feed"]
            if rate != 104 or skipped or accepted != attempts or attempts + remaining != ticks:
                raise ValueError("Stationary fixture cadence/admission differs")
            if not active:
                if attempts != ticks or remaining:
                    raise ValueError("Stationary fixture feed stopped early")
                if receipt["virtual_us"] - initial["virtual_us"] < ticks * 1000000 / 104 - 1:
                    raise ValueError("Stationary fixture ran faster than configured ODR")
                return receipt
            await asyncio.sleep(2)

    active = False
    try:
        async with asyncio.timeout(timeout):
            await running(False)
            await ok("SET ODR 104")
            await ok("SET ACCEL_FSR 2")
            await ok("SET GYRO_FSR 1000")
            active = True
            await ok("FUSION START")
            await running(True)
            if (await model("inject", fixture))["accepted"] is not True:
                raise ValueError("Stationary producer did not activate sensor")
            first = await snapshot(1)
            validate_fusion(first, fixture)
            await feed(100)
            before = await snapshot(101)
            validate_fusion(before, fixture)
            await feed(160)
            ready = await snapshot(261)
            if not ready["ready"] or ready["up_side"] != 2:
                raise ValueError("Stationary window did not establish upright readiness")
            if any(abs(v) > .001 for v in ready["gyro_dps"]):
                raise ValueError("Stationary window did not remove fixed gyro bias")
            if any(abs(v - expected) > .1 for v, expected in zip(ready["accel_mms2"], (0, 0, 9806.65))):
                raise ValueError("Stationary calibration changed acceleration units")
            if not first["timestamp_us"] < before["timestamp_us"] < ready["timestamp_us"]:
                raise ValueError("Stationary source time did not advance")
            if await request("FUSION GET") != ready["line"]:
                raise ValueError("Stationary snapshot read changed publication")
            await ok("FUSION STOP")
            await running(False)
            disabled = await model("state")
            if disabled["feed"][0] or any(v >> 4 for v in disabled["controls"]):
                raise ValueError("Stationary stop retained feeder/sensor activation")
            await ok("FUSION START")
            await running(True)
            if (await model("inject", fixture))["accepted"] is not True:
                raise ValueError("Stationary reopen did not activate sensor")
            reopened = await snapshot(1)
            validate_fusion(reopened, fixture)
            if reopened["timestamp_us"] <= ready["timestamp_us"]:
                raise ValueError("Stationary reopen retained an old source timestamp")
            await ok("FUSION STOP")
            await running(False)
            active = False
            await ok("SET ODR 833")
            record["status"] = "PASS"
    except BaseException as error:
        record["status"] = "FAIL: " + type(error).__name__ + ": " + str(error)
        raise
    finally:
        try:
            await model("feed_stop")
        except BaseException:
            pass
        if active:
            try:
                await ok("FUSION STOP")
            except BaseException:
                pass
