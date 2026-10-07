<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Follow-up contracts after queued-destination qualification

These are proposed work, not implemented or qualified capabilities. Start from
the current reviewed firmware head and consult
`CrispStrobe/brickwright-spike-prime-fw/docs/project/tx-link-qualification.md`.
Do not credit queue-time generation capture with atomic transport admission.
Preserve retained attribution, compiler-input inventories and mandatory gates.

## T01 — Bind final transport admission to a connection instance

The [BLE admission candidate](ble-session-qualification.md) records a bounded
implementation and its required qualification. Classic lifetime protection and
the rest of this lane remain open.

Owner repository: `CrispStrobe/brickwright-spike-prime-fw`.
Entry points: `bluetooth/zephyr_compat/include/brickwright/hub_transport.h`,
`bluetooth/zephyr_compat/src/hub_transport.c`,
`bluetooth/zephyr_compat/src/classic_spp.c`, `apps/btsensor/btsensor_tx.c`.

Define a bounded connection token containing destination and non-reusable
identity. Final admission must accept only the originating live connection.
Capturing the current generation, unlocking and then sending through a mutable
global connection does not meet this contract. Retain/refcount a concrete
connection where supported; otherwise serialize connection replacement and
admission with documented lock ownership. Review callback reentry and lock
ordering before adding locks across a Bluetooth send. Reject stale tokens
without placing their payload on a replacement connection or the other link.
Preserve the existing all-or-error contract or explicitly implement and test
partial acceptance; do not interpret a positive byte count as a refusal.

Acceptance: force disconnect/reconnect between pending-copy and final admission,
including same-link replacement and simultaneous other-link traffic. No stale
bytes reach the replacement peer. Exercise disconnect/reentry from the fake
send callback and real compiled guest reconnect. A mutation bypassing the final
token check must be detected by observable payload/peer comparisons. Both clean
protected profiles and mandatory input/link/resource/TI/matrix checks must pass.

## T02 — Preserve asynchronous producer origin and terminal reply admission

Owner repository: `CrispStrobe/brickwright-spike-prime-fw`.
Entry points: `apps/btsensor/btsensor_classic.c`,
`apps/btsensor/btsensor_main.c`, `apps/btsensor/btsensor_tx.c`,
`apps/btsensor/btsensor_modern_backend.c`.

Capture T01's connection token when accepting each asynchronous command. Retain
it through completion, cancellation and enqueue; never substitute the current
session at completion. Give terminal replies a documented bounded admission
policy distinct from replaceable periodic telemetry. Classic JSON currently
uses the frame queue, so merely prioritizing the separate ASCII response queue
does not satisfy this contract. Define what happens when terminal capacity is
unavailable before starting work; do not silently claim guaranteed delivery.

Acceptance: finish an old motor job after reconnect; no reply appears in the
new session. Fill telemetry capacity while jobs complete; admitted terminal
replies survive and retain exactly-once behavior. Rejected jobs have explicit
errors and no new motor action. Test cancel/complete races, both-link pressure,
maximum supported reply sizes, queue exhaustion and recovery. Mutations that
replace the origin token or permit telemetry to evict terminal replies must fail.
Run actual compiled guest single-link and overlapping BLE/Classic scenarios.

## T03 — Give drain timeout registrations an identity

The [drain registration candidate](drain-registration-qualification.md) records
the identity-bearing API, its host controls and remaining guest/provider boundary.

Owner repository: `CrispStrobe/brickwright-spike-prime-fw`.
Entry points: `apps/btsensor/btsensor_tx.c` and its timer callers/tests.

Specify a generation/token for every drain registration and timer arm. A stale
timer callback or an old cancellation must not finish or cancel a replacement
registration, including replacement initiated by a callback. Define ownership
through init/deinit, disconnect and callback reentry. Keep waits bounded and
callbacks outside locks wherever their reentry contract requires it.

Acceptance: deterministic fake-timer schedules cover old expiry after cancel,
replacement before old expiry, cancellation racing arm, drain racing expiry,
init/deinit racing completion, and callbacks registering replacement waits.
Each registration produces at most one permitted completion and replacement
waits remain live. A mutation removing identity validation must be detected.
Qualify affected ARM callers after any source change; host controls alone do
not authorize firmware merge or desktop adoption.
