# Physical qualification plan

Physical qualification is pending. The current source and CI remain
simulation-only and publish no flashable firmware artifacts. This document
records the evidence required to close the existing C5/C6/C7 hardware gates;
it does not authorize a hardware release or record tests that have not run.

The [current-state handover](next-steps.md#l13-physical-qualification-and-release-decision)
assigns this work to L13 and separates preparation from experiments that require
identified hardware and an operator.

## Prerequisites and evidence

Use an identified hardware revision, firmware source/configuration hashes,
reviewed build inputs and retained notices. Keep the exact physical controller
service-pack source/hash and its chip-restricted licence separate from the
TI-free simulation profiles. Record instrument/setup identification, stimulus,
expected behaviour, actual observations and uncertainty for every result.
Use supervised, current-limited fixtures and a defined independent motor-stop
mechanism for powered motion tests.

| Gate | Experiment and observable acceptance evidence |
|---|---|
| Boot/recovery | Repeated cold/warm boots and reset during initialization; bounded successful startup or explicit recoverable failure, with unpowered motors |
| Controller lifecycle | Actual CC2564C initialization, eHCILL sleep/wake, shutdown, reset recovery, baud change and ACL flow control; preserve the imported service-pack byte stream |
| Bluetooth interoperability | Classic pairing/RFCOMM and BLE advertising/pairing/GATT on identified Linux/macOS/Windows clients; reconnect after host and hub restart; recorded persistent-key behaviour |
| Port identity | Attach/remove each supported motor/sensor on A–F; reject wrong/stale identity and mode, avoid applying motor PWM to a sensor |
| Motor control | Independent angle/rate measurements for timed/degree/position operations, both directions and counter wrap; measured stop latency, cancellation, power fault and watchdog behaviour |
| Stall/HOLD | Define measured capability and thresholds first; require successful physical controller evidence before exposing these options |
| IMU | Independently known poses/motions, scale and axis calibration, drift, timestamp behaviour and yaw reset/base semantics; pair raw protocol frames with observations |
| Storage | Independent supply interruptions during native/Python program and calibration save; cold reboot restores old/new complete state, preserves nonblank damaged media and reports failures |
| Power/thermal | Measured battery ADC/temperature inputs, low-power response, overcurrent/thermal transitions and shutdown; no guessed healthy values |
| Resources/recovery | Measured stack/heap high-water marks, queue saturation, latency under concurrent device/radio activity, repeated failure recovery and documented long-duration runs |
| Release review | Review results, remaining defects, attribution/configured-build inventories, controller distribution boundary and a documented go/no-go decision |

## Limits of current evidence

Real pinned LittleFS host crash/restart tests model NOR write interruption but
substitute the NuttX VFS and physical supply/controller. Synthetic motors and
IMU poses prove software behaviour under declared inputs, not real control
accuracy, physical brownout recovery or RF/electrical behaviour. The current
virtual HCI controller does not establish physical service-pack/controller
initialization. No physical gate above is closed by this repository's current
simulation results.
