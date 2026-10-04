# Modern IMU reference captures

Modern BLE IMU emission remains unqualified. The published
[SPIKE protocol inventory](https://github.com/LEGO/spike-prime-docs/tree/446549146df626f5d7f332b0ea3cd0205ce23711)
defines a 21-byte IMU record with two face identifiers and nine signed
little-endian 16-bit fields. It does not establish the conversion scales,
Euler conventions, yaw-face selection or yaw-reset behavior needed here.
The two inspected callers also disagree on scaling their angle values.
See the [BLE inventory](ble-protocol.md) for the caller provenance.

## Offline decoder

From the repository root, run:

```sh
python3 simulation/bluetooth-air/imu_reference.py .local/imu-captures/reference.jsonl
python3 tools/test_imu_reference.py
```

The decoder reads a file without contacting a device or network. Store captures
and opaque reference firmware privately under the ignored `.local/` directory.
Reference images are not repository dependencies or redistribution artifacts.

The first JSONL line describes the declared source:

```json
{"schema":1,"kind":"metadata","declared_source":"reference","firmware_version":"observed release","firmware_image_sha256":null}
```

Use `synthetic` for constructed fixtures. The optional image hash must be null
or 64 hexadecimal characters. A version or hash supplied by the user does not
authenticate the source. Subsequent lines each contain one complete SPIKE COBS
DeviceNotification frame:

```json
{"kind":"notification","experiment":"static-top","timestamp_us":0,"frame_hex":"complete encoded frame in hexadecimal"}
```

The placeholder above must be replaced with actual frame bytes, including the
terminator. Timestamps must be nonnegative integers and strictly increase
throughout the file. Experiment labels group observations; they do not assert
which physical motion occurred.

The report preserves raw record bytes and exposes `yaw_raw`, `pitch_raw`,
`roll_raw`, `accel_raw` and `gyro_raw` without scaling or axis conversion.
It always sets `wire_mapping_qualified` and `provenance_verified` to false.
Unknown or truncated records, duplicate JSON fields, invalid face identifiers,
invalid lengths and exceeded bounds reject the entire capture without partial
standard output. Bounds are 8 MiB of input, 8 KiB per line, 1,200 frames,
1,200 encoded bytes per frame, 1,024 decoded bytes per message and 10,000 records.
At least one IMU record is required.

## Evidence still required

Qualification needs paired raw notifications and independently known reference
inputs or reference API observations. Cover static gravity and all faces,
positive and negative rotations around each axis, mixed rotations in both
orders, angle wrap and pitch singularities, several angular rates, supported
yaw faces and yaw resets. Record API errors and quantization as well as normal
results. Synthetic fixtures qualify decoding only.

The unchanged private SPIKE 1.8.149 application reached ADC, DMA and display
initialization in a bounded emulator preflight on 2026-10-04. Its first CRC
write then crashed the STM32F4 model through an absent optional reversal field.
No modern IMU notifications were captured. External SPI flash was unseeded;
full boot, Bluetooth startup and reference wire behavior remain unqualified.
The preflight did not patch the application or use display hooks.

The application SHA-256 was
`1f9eb66554fd0f3ea8d0475e796ef32d8fb1bc84713d5deeab1c667e421d89a6`;
the application slice loaded at `0x08008000` was
`37e2e4dc997f3bf16bbf17e424c4ff1c15a4809e40066f0e747cc78a58795861`.
These identify that preflight, not a successful oracle qualification. The
decoder does not verify either image.
