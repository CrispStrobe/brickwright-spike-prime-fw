# Legacy btsensor command adapter

The active legacy ASCII parser is independent of Bluetooth and NuttX. Classic
RFCOMM supplies bounded lines, the parser calls `btsensor_peripheral_ops`, and
the existing tagged TX arbiter returns the reply on the selected link. A
simulator can install the same operation table without emulating a CC2564C or
TI service pack.

| Command | Neutral operation | Reply compatibility |
|---|---|---|
| `PING` | none | `OK PONG` |
| `IMU ON/OFF` | enable IMU stream | `OK`, `ERR busy`, `ERR invalid …`, or `ERR errno=N` |
| `SENSOR ON/OFF` | enable peripheral stream | same |
| `SET ODR/ACCEL_FSR/GYRO_FSR value` | configure IMU | same |
| `GET ODR/ACCEL_FSR/GYRO_FSR` | read raw driver-compatible enum index | `OK index` or `ERR errno=N` |
| `SENSOR MODE class mode` | select peripheral mode | standard result |
| `SENSOR SEND class mode hex…` | raw bounded mode write | standard result |
| `SENSOR PWM class values…` | write one to four raw duty channels | standard result |
| `_IMU_CAP START [seconds]`, `STOP` | calibration-capture lifecycle | standard result |

Class names and numeric IDs remain `color=0`, `ultrasonic=1`, `force=2`,
`motor_m=3`, `motor_r=4`, and `motor_l=5`. Payloads remain limited to 32 bytes,
PWM values to -10000 through 10000, modes to 0 through 7, and capture duration
to 86400 seconds. Fragmented input, CRLF, independent link buffers, overflow
recovery, strict numeric/hex parsing, and backend errno propagation have native
tests.

Fixed-arity commands reject trailing tokens. `SENSOR SEND` and `SENSOR PWM`
are the only variadic commands because their remaining tokens are respectively
payload bytes and PWM channels.

The two per-link assembly buffers prevent a fragmented Classic record from
contaminating another link's record, but they are not synchronization objects.
Production delivery is serialized by the Zephyr host receive work queue, and
the selected-link plus response enqueue sequence relies on that ownership.
Simulator and alternate transport adapters must likewise invoke the receive
callback serially; concurrent calls require serialization above this adapter.

The adapter deliberately does not expose the old `MODE SHELL`, arbitrary
MicroPython/REPL, filesystem, or capture-byte-stream transports. Those are not
peripheral operations in the finite hub contract. A NuttX backend still has to
connect this table to the existing IMU, LEGO-port, bundle, and capture services;
until then a missing callback fails as `ERR errno=95` rather than succeeding as
a no-op.
