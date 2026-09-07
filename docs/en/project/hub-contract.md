# Transport-neutral hub contract

`protocol/hub-contract.schema.json` is the canonical seam between hardware
drivers, Bluetooth/USB transports, and the Brickwright simulator. It describes
logical hub state and operations; it contains no HCI, RFCOMM, ATT, GATT, COBS,
JSON-line, Scratch Link, or TI-controller concepts.

## Envelope model

Every message has protocol version `1`, a kind, and a session identifier:

- a `request` contains a client-selected operation ID, operation name, and
  arguments;
- a `result` repeats the operation ID and contains either a value or a stable
  error object;
- an `event` contains a monotonically increasing sequence number, event name,
  and value;
- a `snapshot` contains the complete observable `HubState` and sequence number.

IDs are opaque strings, not integers with transport-specific widths. A new
connection has a new session ID and event sequence starts at zero. Results from
an old session are discarded. Events are ordered within a session; detecting a
gap requires a new snapshot.

## State and units

The state model covers:

- six ports (`A` through `F`) with attachment identity and one typed motor,
  color, distance, force, or 3x3-matrix state;
- yaw/pitch/roll, acceleration, angular velocity, orientation, and gestures;
- the 5x5 hub display, three buttons and their pressed state, center RGB light;
- sound volume/activity;
- battery percentage, voltage, current, temperatures, charging, and low-power
  state;
- storage capacity/free space and a metadata-only file listing;
- connection, fault, and motor-failsafe state.

Angles and motor positions are degrees, motor angular velocity is degrees per
second, acceleration is milli-g, distance is millimetres, voltage is
millivolts, current is milliamps, temperature is degrees Celsius, sound
frequency is hertz, and durations are milliseconds. Percentages are integers
from 0 through 100. Timestamps are monotonic milliseconds since boot, not wall
clock time.

Unknown and unavailable values are represented by absence, never invented
defaults such as 100% battery. Port attachment changes replace the complete
typed port value and increment its generation so stale commands can be
rejected.

## Operations

The version-one operation vocabulary is deliberately finite:

| Family | Operations |
|---|---|
| session/state | `hub.get_snapshot`, `hub.subscribe`, `hub.unsubscribe`, `hub.stop_all` |
| motor | `motor.run`, `motor.run_for_time`, `motor.run_for_degrees`, `motor.run_to_position`, `motor.stop`, `motor.reset_position`, `motor_pair.configure`, `motor_pair.move`, `motor_pair.stop` |
| 5x5 display | `display.set_pixels`, `display.set_pixel`, `display.clear`, `display.write` |
| 3x3 matrix | `matrix3.set_pixels`, `matrix3.set_pixel`, `matrix3.clear` |
| light | `light.set_rgb` |
| sound | `sound.beep`, `sound.stop`, `sound.set_volume` |
| IMU | `imu.reset_yaw`, `imu.preset_yaw` |
| sensor | `sensor.configure`, `sensor.set_distance_lights` |
| storage | `storage.list`, `storage.read`, `storage.append`, `storage.delete` |

The schema closes the envelope, operation vocabulary, state shape, units, and
ranges. C2.4's codec layer owns the per-operation argument variants and will
reject unknown fields as well as invalid ranges, absent devices, stale port
generations, busy resources, and unsupported capabilities with a stable error
code. Arbitrary Python, shell commands, memory access, firmware update, and
unrestricted paths are not operations in this contract.

Storage is optional and sandboxed. Names are single path components, reads are
bounded, and data is base64 in JSON representations. Firmware-update and
bootloader operations will require a separate authenticated protocol if added.

## Events and snapshots

An implementation may coalesce high-rate samples, but must not reorder them.
The event vocabulary is `hub.state`, `port.changed`, `button.changed`,
`gesture.detected`, `battery.changed`, `fault.raised`, and `operation.completed`.
Long-running motor operations return an accepted result and later emit
`operation.completed`; stopping or disconnecting completes them as cancelled.

`hub.subscribe` selects event families and a requested minimum interval. The
implementation may use a slower safe interval and reports the effective value.
Snapshots are the recovery mechanism after connect, reconnect, or event loss.

## Safety and lifecycle

Motor commands include an end action (`coast`, `brake`, or `hold`) and may
include speed, acceleration, deceleration, stall detection, and a bounded
deadline. Firmware clamps only where the operation explicitly permits it;
otherwise invalid values are rejected.

Loss of the controlling session, expiry of its watchdog, fatal parser/resource
errors, or explicit `hub.stop_all` stops all motors and sound. This invariant
belongs to the hub core, below every transport. A simulator must expose the
same transition and completion events.

## Compatibility mapping

Legacy Classic JSON command names and modern BLE tunnel JSON are adapters into
this vocabulary. Their state messages are projections of the same `HubState`.
An adapter may report `unsupported` for deferred features, but must never turn
an unsupported operation into successful no-op behaviour.

The initial compatibility target implements state/snapshot, motors, displays,
lights, sound, IMU, core sensors, buttons, battery, and safe disconnect. Storage
is specified but optional. Python/REPL compatibility remains outside this
contract.
