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
