# Firmware capability matrix

This is the current implementation and evidence map for Brickwright's
experimental NuttX firmware. A protocol vocabulary or a passing model test does
not establish a complete firmware feature. Physical hardware qualification is
open. The `simulation` and `simulation-hci` profiles are the same firmware;
the latter enables startup against an explicitly connected virtual HCI
controller. Neither includes the TI service-pack payload.

The firmware derives from spike-nx and retains credited permitted Pybricks
robotics components, alongside MicroPython and selected Zephyr Bluetooth host
code. It is not a complete clean-room firmware or a dependency-free rewrite.
See [provenance](provenance.md), the repository's `THIRD_PARTY.md` and the
[configured-build qualification](simulation-qualification.md).

## Firmware boundaries

| Firmware | Relationship and current evidence |
|---|---|
| Original spike-nx NuttX baseline | Source ancestor with existing board/drivers/apps. Its rebuilt protected pair separately reached unchanged reset, kernel start, late initialization and board bringup milestones; this does not qualify every original feature or radio path. |
| Brickwright NuttX fork | Adds the bounded program/MicroPython service, selected Zephyr Bluetooth integration, transport adapters and simulation qualification described below. |
| Stock LEGO reference image | Separate unchanged private oracle; neither a repository dependency nor a redistributed artifact. Bounded execution has not established complete boot or modern IMU notifications. |
| Pybricks firmware | Separate robotics firmware project; selected credited sources remain in our fork. Entire firmware/API parity and total source replacement are not claimed. |

The original baseline milestone results are recorded in
[the simulation README](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/simulation/renode/README.md). Our two simulation
profiles are configurations of Brickwright, not independent firmware projects.

## Observable capabilities

“Host-tested” means actual firmware C code exercised with synthetic boundaries.
“Guest-tested” means compiled ARM firmware executed in Renode. Neither means
physical hardware or original LEGO API compatibility. The latest source
candidate's clean build and guest results are recorded separately in
[simulation qualification](simulation-qualification.md).

| User-visible behaviour | Current implementation and evidence | Remaining work |
|---|---|---|
| Boot and local execution | Protected NuttX kernel/userspace; normal and erased-first-boot storage fixtures; local program service starts without radio | Hardware boot, electrical and recovery validation |
| Upload, commit, save and load | Native instruction and embedded MicroPython programs; bounded owner-bound uploads, CRC, transactional replacement, fixed LittleFS slot; host and earlier guest save/reload evidence | Full LEGO Python/module compatibility is not implemented |
| Run, stop and run again | Retained READY/COMPLETE/STOPPED/FAULT programs can restart with fresh state; timeout/cancellation/device errors remain distinguishable; host regressions and actual ARM retained native/Python restart workflow | Wider program/API compatibility and long execution/fault sequences |
| Autonomous motor movement | A–F addressing with supported attached motor identities; encoder-feedback relative positions, bounded demand, settling requirement and owned braking; host device fixtures, default A/B arena and separately qualified six-motor topology | Current-candidate six-motor regression, physical servo tuning and position hold |
| Classic Bluetooth degree moves | Actual signed encoder displacement for UART motor types 48/49; modular counter wrap, bounded polling, timeout/no-progress failure and tagged end action; host fixtures across A–F | Guest motor-coupled degree exercise, additional motor types, precise positioning/deceleration and timestamped encoder ABI |
| Disconnect and cancellation | Session-controlled Classic jobs stop owned motors; stale ownership cannot stop a replacement; attachment-loss cleanup attempts unpinned coast while preserving failure | Physical motor-safety/fault/soak tests; autonomous programs intentionally survive a transport disconnect |
| Stall detection and HOLD | Explicitly unsupported where the backend cannot guarantee the requested behaviour; stationary/no-progress degree failure is a timeout policy | A specified measured stall detector and persistent position-hold controller |
| Sensors and port discovery | Native port discovery; program API covers color/reflection on C, distance on D and force on E; unavailable samples fail | Arbitrary six-port sensor addressing, additional identities/modes and attachment-generation conformance |
| Display, light and sound | Firmware backends and selected Classic/modern command fixtures; native display clock routing has model evidence | Full operation/state projections and physical fidelity |
| Bluetooth connection and peers | Virtual HCI startup; direct LE reconnect, Scratch Link, Classic, stationary IMU, pose IMU and calibration peers pass the current complete matrix | Cold-restart bond reuse, wider pairing/security/interoperability and physical controller/RF |
| IMU fusion and application axes | Coherent timestamped snapshots, stale/invalid sample rejection, six synthetic poses and declared base projections | Motion/heading drift and physical calibration evidence |
| Calibration save/load | Fixed mounted LittleFS path; synchronized temporary + atomic replacement; exact/finite/nondegenerate record validation; host failure injection, 63 real LittleFS crash/restart cases and actual ARM save/load/reopen peer | Cold guest reboot and physical power-loss behaviour; native settings record has no checksum/authentication |
| Live stationary thresholds | Validated signed-16-bit raw representation; load revisions refresh the detector at unchanged sensor configuration; invalid scaled values make samples unavailable; sanitizer fixtures | Physical threshold calibration and motion discrimination |
| Modern LEGO IMU wire mapping | Offline raw-record decoder; synthetic decoding and pose evidence | Independent paired reference notifications and known inputs; units, Euler/yaw-face/reset conventions remain unqualified |
| Battery, temperature and power | Selected modeled notifications and fixtures | Documented native ADC inputs, complete power-management behaviour and physical validation; unknown state must not become invented values |
| Original LEGO firmware execution | Private unchanged reference image; earlier bounded execution on public hardware models | Complete boot, Bluetooth startup and reference IMU notifications; see [reference evidence](imu-reference-captures.md) |

## Ordered remaining work

For independently assignable tasks, source entry points, dependencies and
acceptance tests, use [the current-state handover and task lanes](next-steps.md).

Both protected profiles, compiler-input licence closures, resource budgets and
all six guest/peer scenarios pass for the source candidate recorded in
[simulation qualification](simulation-qualification.md). Continue with:

1. Couple the new Classic degree path to measured guest motor feedback; extend
   the default A/B-motor/C/D/E-sensor arena using the existing separately
   qualified six-motor profile. Rerun that profile on this candidate before
   extending the supported sensor layouts.
2. Specify and implement arbitrary-port sensor reads and state projections with
   attachment generations, freshness and stable unsupported errors. Extend
   timed/degree cancellation and fault cases across transports.
3. Collect independent modern IMU evidence using the experiment plan in
   [reference captures](imu-reference-captures.md). Keep the wire emitter gated
   until a separately reviewed mapping is supported by held-out observations.
4. Continue unchanged-reference bringup only from demonstrated public peripheral
   contracts. Open model gaps include DMA interruption flags, ADC overrun,
   memory remapping and native battery/temperature inputs; do not use guessed
   healthy readings, patched application bytes or invented flash initialization
   to manufacture successful boot.
5. Test bond persistence through a cold guest restart, resource exhaustion,
   latency/recovery and longer simulation fault sequences.
6. Follow the [physical qualification plan](hardware-qualification.md) separately. A simulator cannot close
   controller/RF, thermal, electrical, motor-safety or physical power-loss gates.

Complete removal of Pybricks-derived robotics code is a separate architecture
project; retained licensed source does not itself prevent the permitted-source
simulation profiles. Every replacement would need behaviour and provenance
review without erasing existing rights-holder notices.

## Pending Classic guest extension

The [measured Classic motor contract](classic-motor-qualification.md) records a
passing complete external A/B fixture on the stack-corrected firmware candidate.
Signed/concurrent displacement, Stop/replacement, loaded timeout and explicit
unsupported errors are now observed through actual guest command handling and
the electrical motor models. This remains a candidate: the current-source
six-motor regression and hosted matrix are pending. It does not supersede the
historical matrix above, qualify arbitrary layouts or establish desktop package
adoption. L01 still owns attachment/disconnect and excluded interleaving work.
