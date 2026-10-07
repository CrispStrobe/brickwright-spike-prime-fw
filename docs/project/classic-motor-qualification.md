# Classic measured motor guest qualification

This is the L01 test contract and partial qualification checkpoint from 2026-10-07.
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

The wire carries the pinned NuttX negative errno values: `ENOTSUP=-138`,
`EINVAL=-22` and `ETIMEDOUT=-110`. NuttX distinguishes ENOTSUP from
EOPNOTSUPP (95); the host C tests use their host libc's symbolic errno and do
not establish an identical numeric ABI. The first complete candidate run
preserves the test's incorrect Linux ENOTSUP expectation as a failed comparison.

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
cause was subsequently isolated with read-only guest observations; cancellation,
replacement and the later no-progress/boundary cases are **not guest-qualified**
by this run. Completion
power zero does not imply instantaneous zero angular velocity or active HOLD.

An isolated Stop run reproduced a NuttX mutex-owner assertion while allocating
an RFCOMM reply buffer. A read-only write watch observed the worker's correct
initial thread ID, then ARM exception stack saves overwriting its TLS before
the assertion. This establishes stack exhaustion in the observed reply path,
not a missing TLS initialization or a successful cancellation. The candidate
reserves 6 KiB instead of 4 KiB for the system Bluetooth work queue and adds an
exact resource-policy bound that rejects both the old value and unreviewed
growth. This adds 2 KiB to that worker's dynamic stack allocation; unchanged
static RAM usage alone cannot establish runtime heap headroom. The corrected
complete peer subsequently passed on the clean candidate. Assertions and the
complete peer gate remain enabled.

On firmware candidate `92ced1c`, the hook-free complete peer passed signed and
concurrent motion, Stop/replacement (-182.244 degrees for -180 requested) and
loaded no-progress (`ETIMEDOUT` after 1,021,052 guest microseconds). It then failed
the first boundary comparison because the peer incorrectly expected Linux's
ENOTSUP number instead of the observed pinned NuttX ABI. That failure is retained;
the corrected complete peer at `52caf015cca2fe8f13b65a1c4b63210830aa1f4d`
then passed against the same clean firmware. This is not an additional firmware
behavior change. Both clean protected profiles passed build/input, linker, TI
and resource gates (592,772 flash bytes, 88,144 static RAM bytes each).

The corrected complete run measured +95.412/-93.416 degrees for signed 90-degree
requests, +189.556/-188.682 for concurrent 180-degree requests, and -182.244 for
the -180-degree replacement after Stop. The fully loaded request failed with
`ETIMEDOUT` after 1,020,241 guest microseconds with no displacement above one
degree and power zero. HOLD/stall returned -138 and zero speed returned -22;
each rejected request left power zero. The shared fixtures observe real modeled
position/power and public load input; they do not set encoder position, pending
job state or completion results.

The current-source native/Python six-motor regression passed all 208 observations
through 15,957 guest milliseconds: A–F speed and position control, simultaneous
six-port activity, native/Python Stop and the unattended-radio reset boundary.
Each -30-degree position result was within the existing three-degree tolerance.
This used the retained installed native Runtime with source-staged pinned models;
it does not establish new runtime source-to-binary provenance.

The [hosted complete matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37595428652)
is incomplete. Its HCI ARM build passed, then the pinned TI fingerprint-reference
fetch failed with an official-server connection timeout before later guest gates.
The default-profile job subsequently failed at the same fetch step after its
ARM build passed. Both hosted jobs therefore remain failed. The failure is
preserved and the TI exclusion gates remain required.

Five existing air scenarios passed locally against the staged HCI image with
harness `52caf015cca2fe8f13b65a1c4b63210830aa1f4d`: Scratch Link, Classic/raw
fusion, stationary readiness, six-face/gyro poses/base axes and calibration
persistence. Stationary readiness became true at sample 261; Stop/restart
returned a fresh sequence-one, not-ready snapshot. Calibration SAVE at sequence
441, then STOP/LOAD/reopen retained the learned gyro bias with sequence one and
readiness reset. This is guest-VFS persistence, not physical power-loss durability.
The corrected LE reconnect scenario separately passed with the host-only harness
`02bb2aefdeb640e95be3685589dd5f5fbe2de5d8` against the same firmware/model inputs.
This split evidence is not a complete canonical matrix on the newer harness
and does not replace the failed hosted matrix.

After the official endpoint is reachable, qualify the current executable/harness
candidate in a new complete matrix run and retain the failed attempt at
`52caf015cca2fe8f13b65a1c4b63210830aa1f4d`. The later LE budget correction below
changes the harness, so rerunning that old source alone is insufficient.
Documentation-only follow-ups do not change firmware or require another local
ARM build. Do not waive the TI gate, substitute an unreviewed reference or merge
before all required guest/peer gates pass.

Nine host peer tests and the existing Classic/backend host gates passed. Four
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

Next work: finish the remaining regression runs and canonical matrix before
merging this candidate. The observed Stop reset is fixed and the complete motor
peer passes on the candidate; preserve its earlier failure and read-only diagnosis.
A separate source lane must specify asynchronous fresh-baseline admission for
immediate sequential jobs, retaining bounded waits, attachment generation,
exactly-once replies and cancellation ownership. Add detach/disconnect and old-job
versus replacement adversaries before broadening L01 completion claims. Do not
substitute guest functions, invent readings or silence error comparisons.

## Existing LE regression observation budget

The initial local run of the existing LE reconnect scenario was **incomplete**:
it passed the first periodic subscription/unsubscription and reconnect silence,
then timed out during the final unsubscribe silence observation. Its measured
pre-subscription reconnect window was 106.871 wall seconds; three subsequent
samples took 77.419 seconds and the required unsubscribe silence was 112.590
seconds. Those required observations plus protocol overhead exceed the old
fixed 300-second per-phase budget. No unexpected notification was recorded in
the completed silence windows; that is not a complete LE pass or a performance
qualification.

The host-only candidate at `02bb2ae` adds the already measured reconnect silence
to the ordinary phase budget, capped at 600 seconds. Ordinary nonperiodic and
first periodic phases retain their 180/300-second bounds; the overall scenario
and outer process bounds remain unchanged. Notification content, sample counts,
quiet-window duration and duplicate/late assertions are unchanged. Firmware and
model bytes do not change. The correction is in
`simulation/bluetooth-air/spike_timeouts.py`; three offline tests include the
actual LE caller and detect restoring its old fixed timeout.

The corrected actual run passed against firmware `92ced1c` with the unchanged
Runtime/model inputs. It verified three 62-percent battery records, unsubscribe
and a 96.395-second quiet window, then resubscribed and observed active traffic
before disconnect. A fresh central received its InfoResponse and completed a
97.398-second pre-subscription window with zero inherited notifications. Its
three new battery records matched, unsubscribe succeeded and the final
98.001-second window had no in-flight or late notifications. Owned-process
cleanup completed with no surviving test processes. These wall durations bound
this synthetic comparison; they do not establish physical radio timing or
simulator performance.

The affected local LE qualification is complete. A new complete hosted matrix
on this newer harness is still required after the external TI fetch is available.
Rerunning the old matrix alone cannot qualify it. Preserve the initial local
timeout and both hosted fetch failures.


## Follow-up task: immediate sequential admission

This is a proposed contract, not implemented behavior. Start at
`apps/btsensor/btsensor_classic.c` (`start_degrees` and the pending-job timer),
`apps/btsensor/btsensor_modern_backend.c` (encoder polling and ownership), their
host fixtures and the external peer above. The initial baseline poll currently
returns `EAGAIN` when the previous move consumed the last UART frame. The passing
fixture's 150 ms settling interval deliberately avoids this gap.

A successor must accept an otherwise valid degree request into an unpowered,
bounded baseline-wait state when fresh feedback is temporarily unavailable.
Use a one-second guest-time admission limit and the existing 20 ms polling
interval as the initial declared contract; qualify these bounds explicitly.
Do not block the Bluetooth worker or retry the user's request at the host.
The request retains its identity, port/session ownership and exactly-once reply
through admission and motion. Invalid/unsupported requests still fail before
admission, and another request for that occupied port returns `EBUSY`.

Before applying PWM, require feedback from the same live attachment and session
that admitted the request. A fresh sample must establish the baseline without
counting prior displacement toward the new target. A detached, replaced or
unsynchronized device must never contribute a cached baseline. The existing
`legoport_info_s.event_counter` exposes confirmed device-type edges; it does not
cover every UART resynchronization or make read-and-PWM atomic. Separate
[PR #38](https://github.com/CrispStrobe/brickwright-spike-prime-fw/pull/38) adds a
host-tested read-time guard, with ARM/guest qualification still pending. Extend
conditional attachment/session admission in coordination with L02 before
claiming the stronger protection required here. Waiting
expires with `ETIMEDOUT` and zero commanded power. Missing devices and malformed
frames retain their explicit errors. The motion progress timeout starts when
powered motion begins, separately from the admission limit.

Stop or disconnect during admission must remove the waiting job without later
powering it. Preserve the existing explicit-Stop success reply convention.
A stale timer, cancellation, frame or disconnected session must not finish or
stop a replacement owner. Failure to arm either the admission or motion timer
must release ownership, leave power zero and resolve each affected request once.
Keep other ports active while one port awaits feedback.

Acceptance requires host adversaries for delayed/missing/malformed feedback,
Stop/disconnect while waiting, detach/replacement, stale callbacks, timer failure
and deadline/counter boundaries. Then run actual ARM immediate +90/-90 sequences
without the fixture settling delay, admission cancellation/replacement and
concurrent A/B activity, observing displacement and terminal power. Rerun both
clean protected profiles, the complete Classic peer and all existing air and
six-motor regressions. Restoring immediate `EAGAIN`, admitting an old attachment
sample or applying power before baseline must be detected by targeted mutations.
Publish exact tested sources, observed admission latency and remaining exclusions;
do not infer physical safety or full L01 completion from these finite cases.
