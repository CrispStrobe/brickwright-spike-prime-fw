# Classic measured motor guest qualification

This is the L01 test contract and partial failure checkpoint from 2026-10-07.
The complete peer has **not passed**. The lane owns the Classic motor peer, its offline
adversaries and optional motor topology selection in
`simulation/bluetooth-air/test_spike_air.py`. It does not change firmware motor
control, dependency pins or other workers' editor code.

## Boundary and inputs

Use our source-built `simulation-hci` kernel and userspace, the pinned Runtime
and Infrastructure, a source-generated empty LittleFS fixture and the existing
virtual Bluetooth air. Send the existing Classic JSON requests over authenticated
RFCOMM. The simulated encryption status proves no cipher or RF behavior.

Attach electrical medium motors to A and B through `CreatePrimeElectricalPorts`.
Read position in degrees, angular velocity in degrees/second, signed power in
percent and elapsed guest time through public model properties. These are
synthetic devices, not physical measurements. Fixture actions may set load or
detach an attachment; they must never write an encoder position, completion,
firmware memory, pending-job state or return value.

Advertising does not establish motor readiness. An external preparatory phase
uses distinct request IDs and records `ENODEV` while discovery is incomplete
and `EAGAIN` while POS-mode selection awaits a UART frame. These rejected
requests must leave power zero. Readiness is bounded to 30 attempts and three
guest seconds per port; an accepted 30-degree move must satisfy the same motion
comparison. The peer retries refused preparation requests only; production
firmware/API errors are not replaced or hidden.

An actual initial run completed preparatory A/B moves and the first positive
move, then the immediate negative command returned `EAGAIN`: the previous job
had consumed the last queued encoder frame. Immediate back-to-back operation
is therefore **not qualified**. The remaining comparison uses an explicit
150 ms guest-time settling/fresh-feedback interval between sequential jobs.
This does not change firmware or retry a failed accepted case. A future fix
needs a bounded asynchronous fresh-baseline contract, ownership/cancellation
adversaries and affected guest builds; it must not invent or reuse a stale
encoder baseline across attachment changes.

## Observable cases

- Positive and negative 90-degree jobs on A, at speed 30 and stop mode brake,
  acknowledge only after measured signed displacement reaches the requested
  distance. Allow one degree of encoder quantization and 20 degrees of overshoot
  for the 20 ms polling/UART boundary;
  record the actual displacement rather than treating a reply as motion proof.
- Start A and B before collecting either completion. Observe both motors moving,
  then require distinct, exactly-once completions and zero power afterward.
- Stop an unfinished long A job, then start a replacement A job. Require the
  cancellation reply and replacement completion once each; the old job must not
  stop the replacement. Cancellation currently replies success, not an
  `ECANCELED` exception.
- With load 100%, a degree job must fail with `ETIMEDOUT` after the declared
  one-second no-progress interval and release power. This is a bounded progress
  timeout, not measured physical stall detection.
- HOLD and explicit stall detection fail with `ENOTSUP`; nonzero degrees at
  zero speed fail with `EINVAL`. Rejected requests must not power a motor.
- Attachment loss must fail the pending move and release its ownership. A fresh
  attachment must accept a replacement job. A disconnected peer must leave no
  powered owned motor; reconnection is a separate peer session.

All wall waits are bounded independently of guest-time observations. Retain
failed invocations, source/model/image hashes, requests, replies and measured
states privately. Public results must contain only synthetic summaries and
public source/CI references. Counter wrap, timer-rearm failure and exact
stale-token interleavings remain explicitly targeted host fixtures unless an
actual guest case naturally reaches them. HOLD is unsupported, not simulated
by this lane. Existing six-motor qualification must remain intact.

## Acceptance

Run the new peer through actual ARM code and the existing six-motor guest
regression on the qualified source. Run `tools/check_btsensor_classic.sh` and
`tools/check_btsensor_modern_backend.sh`. Offline adversaries must reject false
completion without motion, opposite direction, duplicate replies, nonzero
terminal power and success on a stalled move. Record every remaining exclusion;
do not mark all L01 cases complete from a partial peer pass.

## Actual checkpoint and reproduction

The source-built HCI firmware at `4e326e7a62624acc865002b256230042d1f50d63`
passed compiler/configuration/linker/notices/TI-exclusion gates, with 592,780
userspace flash bytes, 88,144 static RAM bytes and zero TI payload bytes. Its
consumed Runtime/model source pins remain `756b684eee56ba698a931a14b3f4885cb8d8ada6`
and `fe4ad383c7392527433783fcec455daa7ddc2bb7`. The local experiment used a retained
qualified managed Runtime; this does not close release source-to-binary provenance.
No control source or consumer dependency pin changed for this test lane.

With peer source `8523877`, the settled sequence measured +94.081 and -95.412
degrees for the signed 90-degree requests. The concurrent A/B 180-degree requests
measured +184.875 and -184.889 degrees, both with power zero at the terminal
observation. Preparatory 30-degree moves also passed. The same run then reset
the CPU during Stop/replacement and timed out waiting for replies. The reset's
cause is under investigation; cancellation, replacement and the later
no-progress/boundary cases are **not guest-qualified** by this run. Completion
power zero does not imply instantaneous zero angular velocity or active HOLD.

Eight host tests and the existing Classic/backend host gates passed. Four
deliberate comparator changes were detected: ignored direction, ignored terminal
power, accepted duplicate replies and accepted success instead of timeout.
Source/reuse/origin/safety policy and strict documentation checks passed. All
setup failures, actual negative results, invocations and raw logs stay private.
[PR #37](https://github.com/CrispStrobe/brickwright-spike-prime-fw/pull/37) remains
the draft implementation/review entry point; it is not a merged capability.

Run `python3 tools/test_classic_motor_probe.py` for the offline adversaries.
The canonical actual-air command remains `tools/test_bluetooth_air.sh` after
building/staging the explicit `simulation-hci` profile and reviewed Runtime;
it runs the new `motors` mode in a separate loopback-only namespace and requires
the complete motor scenario. It does not weaken that gate for partial results.
The diagnostic peer accepts `--motor-case motion`, `cancel` or `no-progress`
with `--motor-runtime` pointing at output from
`tools/stage_classic_motor_topology.py --runtime "$RENODE_DIR" --output .local/motor-topology`.
Direct diagnostics must use the same network isolation as the canonical wrapper.

Next work: reproduce the Stop reset with passive assert/hard-fault/reset hooks
and the own firmware's RAM log, identify the actual failing boundary, add a
failing host regression where possible, and qualify any source/model fix with
affected clean guest builds. Separately specify asynchronous fresh-baseline
admission for immediate sequential jobs, preserving ownership and cancellation.
Do not solve either failure by substituting guest functions, inventing readings,
silencing the error comparison or changing reference firmware bytes.
