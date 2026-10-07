<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Encoder attachment snapshot candidate

This is an unmerged integration follow-up to
[the Classic motor qualification](classic-motor-qualification.md). Its exact
attachment-change interleaving is host-tested only. It changes the retained NuttX backend;
no clean-room or whole-firmware independence claim is made.

## Problem and contract

A device connection can change while the backend polls UART position frames.
The existing `legoport_info_s.event_counter` records confirmed device-type edges;
a disconnect and same-type reconnect can restore type/flags while advancing that
counter. Previously a collected frame could be returned successfully across
this observed change.

Bracket motor validation and frame collection with the existing device-info
interface. If a connection edge or loss of UART/connected identity is detected,
return `ESTALE` and leave the output zero. A failed closing device-info read
propagates its error without publishing a position. A later stable attachment
can supply a new frame. Ordinary missing feedback still returns `EAGAIN`;
unsupported mode/type and malformed frames retain their explicit errors.
The zero-output guarantee covers reads with valid arguments; invalid arguments
return `EINVAL` with no output guarantee, preserving the existing API.
No cached frame, PWM demand or ownership state is introduced by this change.

The edge counter is not an absolute physical identity or a LUMP synchronization
generation. Undetected disconnects, unchanged-type UART resynchronization and
an entire counter cycle between observations are outside this guard. The API
still has no frame capture timestamp. Most importantly, the read and later PWM
operation are separate transactions: this candidate does not close their race
or implement the proposed asynchronous sequential-admission contract. L01/L02
must establish conditional admission and attachment/session ownership before
claiming that stronger protection.

## Host evidence

`tools/check_btsensor_modern_backend.sh` fails against the unchanged backend when
the synthetic I/O seam supplies a valid frame and a same-type connection edge
during its collection. The candidate passes that regression, including an edge
from `UINT32_MAX` to zero, fresh stable-frame recovery, detach during collection,
and a closing device-info I/O failure. Each rejected read leaves its output zero.
The existing six-port backend and Classic adapter host suites also pass.

Two compiled mutations fail the comparison: ignoring the event counter and
publishing the candidate position before validation. These are host observations
through the existing I/O seam, not actual ARM/attachment evidence. Retain the
initial failure and unchanged raw receipts privately.

## Clean ARM and guest regression checkpoint

Both protected profiles were rebuilt from
`4ca642c376ea6b35845d09669e18cbeb43ca6a94`. Compiler/configuration, linker,
reviewed source-input and notice checks, resource budgets and local TI-exclusion
checks passed. Userspace flash is 592,860/654,336 bytes and static RAM is
88,144/98,304 bytes; the synthetic TI payload is zero. This adds 88 flash bytes
over the qualified predecessor without changing static RAM. The configured
inventories retain their historical image/link records; the new private build
receipts are separate evidence and do not rewrite those records.

The complete Classic electrical-motor peer passed on the new HCI image with
the consumed Runtime/model pins from the Classic qualification. Requested
signed 90-degree moves produced +94.752/-94.746 degrees; concurrent signed
180-degree moves produced +183.526/-183.891 degrees. Stop followed by replacement
produced -182.903 degrees. These satisfy the documented signed displacement
tolerance. Full load produced `ETIMEDOUT` after 1,018,011 guest microseconds;
unsupported HOLD/stall and zero-speed rejection checks also passed. Existing
terminal power and exactly-once completion checks remained enabled.

The default-profile native/Python six-motor regression also passed: 208
observations through guest clock 15,957 milliseconds, including A–F speed and
position control, six concurrent motors, native/Python Stop and the long-run
reset boundary. Signed -30-degree position targets remained within the
fixture's 3-degree tolerance. This used source-staged models and the retained
installed native Runtime; it does not qualify a newly assembled desktop package
or change a consumer dependency pin.

This regression does not exercise the exact attachment-change interleaving:
that remains host-only. It uses the retained qualified compiled Runtime, not a
new Runtime source-to-binary qualification. The official TI endpoint still
times out; the separate mandatory hosted fingerprint revalidation remains
blocked and has not been waived.

## Qualification still required

Extend the external Classic electrical-motor fixture with public detach and
reattach inputs, observing real guest results, displacement and released power.
Require no success across the observed attachment change and a working fresh
replacement request. Rerun the affected motor regressions after any further
source/model change, and run the full existing air suite on this candidate.
Record exact firmware, harness and
model pins and tolerances. Do not copy the predecessor's successful guest results
onto this source, merge on host tests alone or waive an unavailable TI gate.

## Detach-fixture prerequisite

Before treating the public model's `Detach()` as an electrical unplug, qualify
its actual GPIO and guest observations. The consumed
[electrical-port model](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/fe4ad383c7392527433783fcec455daa7ddc2bb7/src/Emulator/Peripherals/Peripherals/UART/LegoLpf2ElectricalPort.cs)
returns from `Tick()` when `Device` is null. The base port's attachment booleans
are explicitly logical indicators, not electrical ID-pin levels. This source
inspection identifies a prerequisite; it is not an observed guest-detach failure.

A paused-model probe of this consumed model confirmed the distinction. With
the ID/UART GPIOs configured as inputs, attached, detached and same-type
reattached observations all read ID1 high, ID2 low and RX low. The logical
attachment indicator changed true/false/true and topology generation advanced
2/3/4. The probe loaded no firmware and advanced no guest time. It establishes
retained sampled input levels across this sequence, not electrical unplug
semantics, a guest disconnect failure or a correct detached voltage policy.
The initial probe used an unavailable machine-child name and failed; the
corrected probe used the public external port handle. Both receipts remain
private and unchanged.

Add model controls for attach, detach and same-type reattach that observe the
ID/UART inputs and H-bridge demand through documented interfaces, including
when no motor object remains. Establish the detached input policy from the
board/driver contract; do not guess levels or write guest connection state.
Then require a real guest DCM disconnect edge, fresh discovery on reattach,
released bridge demand and isolation of a replacement from the old job. Logical
topology generation alone cannot establish that these electrical/guest effects
occurred. Keep the exact read-time interleaving host-only unless a natural guest
run actually observes it; ordinary detach error handling is a separate result.

Reproduce the host checks with:

```sh
bash tools/check_btsensor_modern_backend.sh
bash tools/check_btsensor_classic.sh
python3 tools/check_source_policy.py
python3 tools/check_reuse_licenses.py
python3 tools/check_source_origin_review.py --require-clearance
```

## Electrical detach/reconnect candidate — 2026-10-07

[Infrastructure PR #35](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/35)
adds synthetic detached ID/RX resolution and read-only bridge-demand observations.
Its source-compiled controls preserve all 35 existing checks; mutations that
retain the detached inputs or hide detached bridge demand are both detected.
[Runtime PR #53](https://github.com/CrispStrobe/renode-spike-prime/pull/53) explicitly
pins the model candidate for canonical build and complete peripheral tests.
Neither candidate has been adopted by the shipped desktop package.

An actual ARM guest using clean protected HCI firmware source
`4ca642c376ea6b35845d09669e18cbeb43ca6a94` and namespace-isolated model candidate
`adf40d98062a6b31aae7ef86e1ae5f289eebdc48` passed one external Classic sequence:

- Start a long powered move, then detach through the public model interface.
  Initial detached bridge demand remains observable; the fixture does not clear it.
- The interrupted job returns `ENODEV=-19`. In 767,803 guest microseconds the
  actual DCM confirmed type changes from 14 to NONE, its event counter advances
  from 1 to 2, CONNECTED clears and bridge demand reaches zero.
- A new request while absent returns `ENODEV` without drive.
- Same-type reattachment creates fresh mechanics. Guest discovery advances the
  counter to 3; a fresh -90-degree job completes at -94.7464 degrees, within the
  external fixture's 20-degree tolerance, and leaves zero bridge demand.
- Unsupported HOLD/stall and zero-speed checks retain their explicit errors.

The harness reads guest diagnostics without writing them. Generate the private,
exact own-kernel debug layout and run the separate scenario after staging models
with Infrastructure's `tools/stage_electrical_attachment_qualification.py`:

```sh
python3 tools/collect_legoport_observation_layout.py \
  --kernel OWN_DEBUG_KERNEL_ELF --output NEW_PRIVATE_LAYOUT_JSON
# Add to the existing explicit Classic motor invocation:
# --motor-case detach --electrical-qualification STAGED_CANDIDATE_DIRECTORY
# --motor-port-layout PRIVATE_LAYOUT_JSON
python3 tools/test_legoport_observation_layout.py
python3 tools/test_classic_motor_probe.py
```

The layout is a hash-bound, six-port read-only diagnostic, not a stable ABI or
an interface for third-party/reference images. Host adversaries reject mismatched
hashes, out-of-range memory and invalid offsets. Model controls, canonical build
results, staged guest results and installed package qualification remain separate.
The final harness additionally embeds candidate/layout receipts in its private
results; the successful guest run preserves the pre-metadata harness snapshot.

This closes one ordinary detach/reconnect sequence in the source-compiled model
context. It does not exercise the exact encoder-read interleaving in the guest,
arbitrary hotplug races, physical unplug safety, transport-disconnect ownership
or canonical-consumer adoption. Repeat affected Classic/native/Python guest tests
on the canonical Runtime candidate, complete the current-source air suite and
satisfy every mandatory gate before merging. The unavailable official TI
fingerprint endpoint remains a blocker, not a waived gate.

### Compiled-model admission and stricter edge checks

The same detach scenario now accepts either the namespace-isolated source
candidate or a Runtime containing the compiled model correction. For the compiled
route, omit `--electrical-qualification`, retain `--motor-runtime` and
`--motor-port-layout`, and supply the exact qualified Runtime build. The default
compiled topology entry point remains `CreatePrimeElectricalPorts`.

Before issuing motor jobs, the peer requires real bridge-drive/brake observations
and a bounded own-kernel DCM identity. An older compiled model missing the bridge
observers fails explicitly with no motor request; it does not fall back to cached
motor power. Private results identify the selected route, model type and module
identity. Those identities are diagnostic bindings, not binary authenticity or a
substitute for the source/build receipt.

The disconnect comparison now also requires a connected, non-NONE prior guest
identity and a detached model afterward; rediscovery must restore the same guest
type with a new counter. Host adversaries reject an initially disconnected guest,
a retained logical attachment and missing/malformed bridge observers. The stricter
comparison passes the exact preserved earlier guest observations. That offline
comparison is not a fresh guest execution or canonical-consumer qualification.

A fresh guest sequence using harness
`ebfdb03d350e22a5ff8fadd29af23b79216cdc00`, the same clean firmware image and
the namespace-isolated model candidate passed these stricter detach/rediscovery
assertions. A separate actual invocation against the retained older compiled
model refused with zero motor requests and zero observed motor power. The latter
is an expected negative admission result, not positive qualification of the new
compiled model. The six-port native/Python scenario also passed with staged
candidate models; compiled-consumer adoption remains separate.

### LE timing qualification gap

The diagnostic air sequence on firmware source
`4ca642c376ea6b35845d09669e18cbeb43ca6a94` and harness
`8409fa9cf9967e0a7dd66a2c926e70e750253ecd` passed the complete Classic motor,
Scratch Link, Classic IMU, pose, stationary/readiness and calibration
save/reopen cases. Fresh compiled admission/edge results above identify their
own later tested harness revision. The LE case failed
inside its unchanged 90-second three-record collector after resubscription before
disconnect. Its first three battery records, unsubscribe acknowledgement/silence
and resubscribe acknowledgement passed; only two active records arrived inside
the next collection bound. Reconnect validation was not reached. The failure is
preserved; neither firmware causality nor full air-suite success is established.

A separate follow-up should record read-only guest-clock progress alongside host
arrival times before changing the observation contract. Preserve three exact
battery records, unsubscribe silence, a fresh central's strict InfoResponse and
zero inherited notifications. Retain finite host/process cleanup bounds and
negative checks for missing/malformed records, clock stalls/regression and leaked
notifications. Do not simply increase a wall timeout to turn this failure green,
force guest time, replace firmware callbacks or infer physical radio timing.
Require an actual current-source air run and preserve the original failure.

The optional `--observe-guest-clock` diagnostic now implements that preparation
for `--periodic --reconnect`. It reads `ElapsedVirtualTime` through the owned
monitor and records host before/after windows every five seconds. These use
the same host monotonic time base as the collector's start and absolute record
arrival timestamps, permitting direct observation-window correlation. Reads have
three-second bounds and a 256-sample cap; regression, malformed values and no
observed progress for fifteen host seconds fail the diagnostic. These host
bounds are instrumentation limits, not firmware timer or physical radio accuracy.
The sampler is joined during success, failure and cancellation cleanup. Host
controls cover a stalled/regressed clock, echoed monitor commands, real command
decoding and cancelled/failed sampler cleanup. Actual instrumented LE results
are recorded below; no observation or cleanup timeout has been increased.

```sh
python3 tools/test_le_clock_probe.py
# Add --observe-guest-clock to the existing explicit --periodic --reconnect run.
```

For direct LE qualification with a compiled Runtime, use `--compiled-board` and
the output of `tools/stage_classic_motor_topology.py`. This selects the same
offline board and aggregate display clock without enabling Classic motor jobs
or including replacement model source. It requires explicit synthetic storage,
matching staged-file hashes and the direct LE route; incompatible transport or
motor options refuse before emulator startup. `--motor-runtime` remains restricted
to the separate Classic motor scenario. Supplied canonical Runtime bundles must
retain their tracked `.renode-root` marker so monitor initialization can load.
Copied platform receipts do not authenticate the supplied Runtime binary.

This battery-only LE scenario starts with empty A–F external ports, matching the
original scenario. The compiled topology's default motors are detached through
public model commands before guest loading/execution; guest DCM state and PWM
are not written. An initial attempt with the default motors attached correctly
failed the exact battery-only payload comparison. That fixture mismatch remains
preserved and does not justify accepting extra/malformed notification fields.

## Compiled consumer checkpoint — 2026-10-07

The canonical compiled Runtime source
[`8f128e66`](https://github.com/CrispStrobe/renode-spike-prime/commit/8f128e66d0be5f83da035eaba9cc4441c0a29a31)
with Infrastructure `adf40d98062a6b31aae7ef86e1ae5f289eebdc48` passed these
actual guest scenarios using the same clean protected firmware source
`4ca642c376ea6b35845d09669e18cbeb43ca6a94`. No replacement peripheral source
was included. NuttX qualifier source was `fa27da11b9654d2e4b54dfb44139cb88975c7d47`;
Classic peer source was `535ac92ea61d71bc52889a7b89c4d6d20b34e916` and direct LE
source was `c2b2eebcdb96691668fefddc20bb8c981deb2734`.

| Scenario | Observed result and boundary |
| --- | --- |
| Classic electrical motors | PASS: signed/concurrent moves, Stop/replacement, load timeout, explicit unsupported/invalid inputs and terminal drive checks. The declared displacement tolerance remains 20 degrees. |
| Detach/reconnect | PASS: `ENODEV`, actual guest type 14 → NONE → 14, counters 1 → 2 → 3, CONNECTED clearing and zero bridge demand after 790,987 guest microseconds. Fresh -90-degree displacement was -95.0791 degrees. |
| Native/Python A–F | PASS: 209 observations covering all six ports, concurrent native/Python activity, Stop and the old unattended-reset boundary. Six position moves stayed within 1.756 degrees of their -30-degree targets, inside the 3-degree limit. Final program clock was 15,997 ms. |
| Supplied upstream MicroPython 1.26.1 | PASS: basic raw-REPL execution/error/cancellation/recovery, GPIO motor/load/cleanup and filesystem reopening in a fresh process. This is not full SDK, USB bootloader or GUI qualification. |
| Direct LE, empty A–F | PASS: exact battery-only notifications, unsubscribe silence, active resubscription, fresh-central strict InfoResponse and zero inherited notifications. Seventeen clock observations stopped cleanly; absolute host arrivals share their monotonic time base. |

An earlier instrumented LE run on the original board fixture also passed both
centrals with 134 clock observations. The preceding timeout remains preserved;
these passes do not establish its cause or physical radio timing. Initial private
compiled-package startup failures caused by an omitted root marker are preserved
separately. Restoring the exact tracked marker supplied the missing initialization
input; original downloaded artifacts, model code and guest bytes were unchanged.

The exact final Runtime candidate also passed its
[canonical build and regression CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37635759307):
448 focused peripheral tests and a complete-suite summary of 566 passed / 5
skipped / 571 total. The raw log additionally reports the pre-existing GIC
inconclusive case as skipped; do not infer that all discovered tests executed.
Native translator, board and free ARM guest checks remained enabled.

These results close the declared compiled-model consumer scenarios. They do not
advance firmware/Lite package pins, qualify an installed GUI, close atomic
encoder/PWM admission or arbitrary attachment/transport races, establish original
reference-firmware boot, or prove physical accuracy. The mandatory firmware TI
fingerprint/matrix gate remains blocked by the official endpoint; no gate is
waived. Keep Runtime/model merges separate from firmware and package adoption.

The next LE lane should define a separate active-port notification contract from
our public firmware protocol and exercise attached motors/sensors, concurrent
traffic and malformed/duplicate records. Preserve this strict battery-only empty
port scenario rather than accepting arbitrary extra fields to make it pass.
