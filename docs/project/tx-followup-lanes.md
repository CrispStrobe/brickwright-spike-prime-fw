<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# TX follow-up contracts and qualification records

These contracts distinguish bounded implemented slices from remaining work.
Use the linked qualification records for exact tested sources and limits. Start
from the current reviewed firmware head and consult
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

Carry that lifetime through downstream queued/deferred send work and completion
callbacks, not only the adapter's immediate send call. Reusing a channel object
must not let old pending work or an old completion act on its new connection.
Document the ownership boundary at the transport implementation as well as the
wrapper; a mutex around wrapper admission alone is not sufficient evidence.

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

## T04 — Qualify degree-command readiness between jobs { #degree-readiness }

Owner repository: `CrispStrobe/brickwright-spike-prime-fw`.
Entry points: `apps/btsensor/btsensor_classic.c`,
`apps/btsensor/btsensor_modern_backend.c`,
`simulation/bluetooth-air/classic_motor_probe.py`. The conditional board boundary
also involves `boards/spike-prime-hub/include/board_lump.h`,
`boards/spike-prime-hub/src/stm32_legoport_lump.c`,
`boards/spike-prime-hub/src/stm32_legoport_chardev.c` and
`boards/spike-prime-hub/src/stm32_legoport_pwm.c`.

The [UART session prerequisite](lump-session-qualification.md) records an additive
feedback identity candidate; conditional motor start and the bounded wait remain
open.

The [drain candidate record](drain-registration-qualification.md) preserves a
local sequential-command failure despite a passing canonical matrix. Reproduce
with immutable candidate/baseline images, identical external inputs and actual
compiled Runtime/model identities. Record refusals as replies, separately from
accepted jobs; do not infer admission from sending a request. Distinguish a
finite passing comparison from a demonstrated causal explanation or a robust
readiness implementation.

Follow the existing [immediate sequential admission contract](classic-motor-qualification.md#follow-up-task-immediate-sequential-admission):
an otherwise valid request enters an unpowered baseline wait with a one-second
guest-time limit and 20 ms polling. Do not retry the user's request at the host,
block the Bluetooth worker, or substitute cached feedback. Invalid/unsupported
requests retain explicit immediate errors; another request for an occupied port
returns `EBUSY`. Start the motion progress timeout only when motion starts.

Qualify the synchronization epoch and conditional board admission first,
including reset/queue invalidation and ABI compatibility. Then wire the backend
reservation and Classic wait; each checkpoint must state whether it is only a
host control or has actual guest integration. Preserve compiler-input manifests,
notices and resource gates for changes to retained drivers.

First provide a side-effect-free reservation and a conditional start boundary
that checks the originating live connection, current port owner, attachment and
UART synchronization identity. Coordinate the kernel/model boundary with L02:
separate read-time identity validation and an unconditional PWM ioctl cannot
prove atomic admission. A DCM device-type edge counter alone does not identify
every UART resynchronization. A changed owner or epoch must refuse the start
without powering or stopping its replacement. Do not wire a deferred
unconditional `tagged_operation` as a substitute for this boundary.

Carry T01's connection lifetime and T02's originating reply admission through
the wait and subsequent job. Stop/disconnect cancels the waiting job without
later motor action; explicit Stop retains its existing success convention.
Admission expiry returns `ETIMEDOUT` with zero commanded power. Failure to arm
either timer releases the reservation and resolves the affected request once.
Keep other ports running while one port awaits a baseline.

Acceptance: cover immediately consecutive degree jobs, simultaneous A/B jobs
followed by cancellation/replacement, missing and delayed UART frames, repeated
admission expiry, disconnect, timer-arm failure, stale callbacks and clock/epoch
boundaries. Preserve all original failed runs.
Distinguish unchanged-input regression from any newly specified readiness-wait
scenario; both need explicit outcomes. Cancellation coverage must first observe
admitted motion and then prove stop and replacement behavior. Mutations that
restore immediate `EAGAIN` for a valid waiting request, power before baseline,
accept stale feedback, duplicate replies or omit the readiness bound must fail.
Run both protected builds and mandatory gates for firmware changes, with
affected compiled guest scenarios and exact source pins.
