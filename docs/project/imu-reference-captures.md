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

After the [CRC correction](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/27),
the same unchanged application completed the formerly crashing stage at
2,220 microseconds of guest time. The old model failed both F4 regression cases;
the explicitly rebuilt model passed all 20 F4/F0/WBA cases. That local diagnostic
reused unchanged dependencies; the separate
[clean Runtime CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37178545076)
rebuilt native and managed sources and passed its model and guest gates.

A separately recorded continuous-scheduling run retained the completed
instruction-step prefix, then completed 10 ms and 100 ms virtual intervals,
reaching 112,220 microseconds of guest time. Its 120-second wall-time bound
expired during the following one-second interval. No fatal exception was
observed, and the observed UART2 output remained empty. The repeated sampled
PC does not establish a cause or prove a guest loop. The application and
peripheral models were unchanged between these diagnostics; changing the execution schedule
provided more guest-time coverage. Full boot and modern IMU wire mappings
remain unqualified.

Passive snapshots of the same legacy board model showed thread-mode execution
with interrupts enabled and no recorded CPU fault. R0 advanced by 72 over a
100 ms virtual interval, despite the repeated sampled PC. R0's meaning was not
established. SysTick was configured at 72 MHz with a reload of 99,999.
The application's observed PLL configuration instead implies a 100 MHz core clock when combined
with the board's 16 MHz oscillator, documented in the
[MicroPython LEGO Hub No. 6 board configuration](https://github.com/micropython/micropython/blob/master/ports/stm32/boards/LEGO_HUB_NO6/stm32f4xx_hal_conf.h).
These observations identify a board-clock mismatch; they do not qualify boot
behavior. No SPI2 write was observed through 412,220 microseconds of guest time,
and the external flash model remained idle.

The longer diagnostic ended with a host `OutOfMemoryException`, rather than a
guest fault. Inspection of the public Renode console implementation showed
that redirected stdin at EOF was repeatedly forwarded to the console queue.
The invocation had used `/dev/null` for stdin. Further runs must hold an empty
input pipe open, or use a separately qualified console correction. Resource
growth in that invocation cannot be attributed solely to guest timer activity.

A repeat with stdin held open and empty completed cleanly through 112,220
microseconds. Its 34 logged TIM12 writes all fit the existing analytical
display-clock model's supported subset. A separate native-profile comparison
then rebuilt the complete current Infrastructure source at
`5d2d3a79ed1df755fc261194de0774960d2ae0d3`, retaining cached diagnostic
dependencies. It used the public profile's 100 MHz clocks, paced 50 MHz SPI2,
native erased flash and analytical TIM12 with the native display. It loaded no
generated boot seed or user program and kept the reference application unchanged.
This differs from the legacy board and is a separate qualification scope.

The native comparison completed the same instruction-step prefix followed by
10 ms, 100 ms and one-second continuous intervals, reaching 1,112,220
microseconds of guest time. SysTick was configured for 1 kHz; R0 advanced by 100
over the 100 ms interval. Sampled execution stayed in thread mode with
interrupts enabled and no recorded CPU faults. TIM12 accounted for 27,747,727
rising edges with 1,128 observer callbacks; it preserves
edge counts without emitting each GPIO pulse. No unsupported TIM12 request or
SPI2 write was recorded; observed UART2 output remained empty. ADC channels
without samples and unmapped SYSCFG accesses were gaps in that pinned
diagnostic revision. Full boot,
Bluetooth startup and modern IMU wire behavior remain unqualified.

A longer run used that same native profile with continuous scheduling directly
from reset. It completed 10 ms, 100 ms, one-second and five-second intervals,
reaching 6.11 seconds of guest time before the 120-second wall bound interrupted
the next ten-second interval. The final completed snapshot still had no CPU
fault or SPI2 write, and observed UART2 output remained empty. R0 continued
advancing; TIM12 accounted for 152,697,729 rising edges with 6,123 observer
callbacks. Peak host memory was about 250 MB. This is additional bounded execution coverage, not
evidence of completed startup or captured IMU notifications.

The preceding reference runs predate the separately tested ADC completion and
SYSCFG EXTICR routing/reset corrections recorded in
[simulation qualification](simulation-qualification.md). Those generic
peripheral tests establish register and board-routing behavior, not a successful
reference application boot. The later DDS=0 DMA terminal-transfer qualification
in that record also covers the synchronous model mechanism only. SYSCFG memory
remapping and native battery/temperature ADC sample sources remain open gaps;
no new reference notifications or modern IMU mapping are qualified here.
