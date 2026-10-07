<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Encoder attachment snapshot candidate

This is an integration follow-up to [the Classic motor qualification](classic-motor-qualification.md),
not a merged or guest-qualified capability. It changes the retained NuttX backend;
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

## Qualification still required

Run both clean protected profiles with compiler/configuration/linker/resource,
licence-input and mandatory TI-exclusion gates. The configured inventories update
only the two changed source-input hashes; their image/link records remain
historical until these builds run. Do not label them new binary evidence.

Extend the external Classic electrical-motor fixture with public detach and
reattach inputs, observing real guest results, displacement and released power.
Require no success across the observed attachment change and a working fresh
replacement request. Rerun complete Classic-air and native/Python six-motor
regressions, then the full existing air suite. Record exact firmware, harness and
model pins and tolerances. Do not copy the predecessor's successful guest results
onto this source, merge on host tests alone or waive an unavailable TI gate.

Reproduce the host checks with:

```sh
bash tools/check_btsensor_modern_backend.sh
bash tools/check_btsensor_classic.sh
python3 tools/check_source_policy.py
python3 tools/check_reuse_licenses.py
python3 tools/check_source_origin_review.py --require-clearance
```
