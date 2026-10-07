<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# BLE final connection admission candidate

This is a bounded part of [T01](tx-followup-lanes.md), not closure of the whole
transport/session lane. Queued BLE output captures a 64-bit connection identity
at admission. Final send validates that identity under the adapter's mutex and
acquires a reference to the concrete Bluetooth connection before unlocking.
Notification and reference release occur outside the mutex. A disconnect can
make this notification fail, but replacement cannot substitute its connection
object for the retained one. The identity counter never resets; exhaustion
refuses traffic rather than reusing an earlier identity.

The TX queue drops an exact stale BLE ticket without counting it as sent, blocking
fresh BLE work or discarding Classic work. Back-pressure retains the original
identity. Legacy immediate BLE sends capture the current identity once and use
the same guarded handoff. The transport API retains its all-or-error semantics.

Lock order: TX admission may hold the queue mutex before the BLE adapter mutex.
The adapter never calls application callbacks, notification or final reference
release while holding its mutex. Connection reference acquisition is the pinned
host's reference-count increment. New controls force same-thread callback
reentry during notification; a lock held across notification would not pass.
The retained pinned host's GATT API takes a concrete connection and rejects
disconnected connections. This candidate does not modify that dependency.

Reproducible host controls:

```sh
tools/check_ble_session.sh
tools/check_btsensor_tx.sh
tools/check_btsensor_tx_links.sh
python3 tools/prove_ble_session_mutations.py
python3 tools/prove_btsensor_tx_links_mutations.py
```

The actual adapter is compiled against neutral connection/notification test
boundaries. Controls cover queued-old-token rejection before notification,
disconnect/reconnect within notification, reference counts before and after the
handoff, argument errors, no-connection errors, a synthetic counter-exhaustion
initial condition, and independent Classic progress. Four compiled mutations
must fail assertions: ignore identity, omit the final reference, or recapture
the current identity at queue send, or discard a Classic refusal as stale BLE.
Compilation failure is not detection;
executables are bounded to ten seconds. These are host controls, not guest proof.

Both configured input inventories refresh only the three changed Apache-2.0
source/header hashes. Licence selections, notices, dependency pins, linker and
resource expectations remain intact. The observations below do not authorize
package adoption; the mandatory matrix remains a separate merge gate.

Classic's mutable RFCOMM endpoint is unchanged and has no equivalent lifetime
guarantee. Asynchronous producers still need originating-session admission;
capturing the current session only when their completion enqueues is insufficient.
Terminal reply capacity, registration/callback ordering and drain/timer races
remain separate work. These finite controls establish neither physical safety,
whole-firmware independence nor general equivalence to another runtime.

Review found that the first candidate applied its new stale-drop rule to
Classic as well. A new control failed on that candidate when Classic returned
`-ESTALE`; the corrected rule drops only stale BLE tickets and preserves the
Classic refusal for retry. The failed comparison and superseded build results
remain preserved. Corrected-source qualification is recorded below.

## Corrected-source qualification

Tested firmware and guest harness source:
`e6f10f9ae8e47ae070693e966e03a7b3d3e18d35`.
Both clean protected candidate profiles passed reviewed compiler/link inputs,
resource limits and local TI exclusion. Observed userspace budgets:

| Profile | Flash bytes / limit | Static RAM bytes / limit |
| --- | ---: | ---: |
| simulation | 595472 / 654336 | 88816 / 98304 |
| simulation-hci | 595456 / 654336 | 88808 / 98304 |

Fresh execution used the actual compiled Runtime source
`8f128e66d0be5f83da035eaba9cc4441c0a29a31` and Infrastructure
`adf40d98062a6b31aae7ef86e1ae5f289eebdc48`, the exact HCI candidate image,
and a diagnostic layout derived from that image's own kernel. No runtime model
source was substituted into these executions. All three scenarios passed:

- Classic motion sequence, cancellation, no-progress, invalid-speed and stall
  refusal controls, including observed motor position and bridge state.
- Detach/reconnect and reattachment controls.
- BLE sensor notifications overlapping Classic motor activity and reconnect.

These executions preserve existing observable behavior; the deterministic host
controls and four detected mutations exercise the forced stale-admission and
reference-lifetime boundaries. A passing guest scenario alone does not prove
all connection races. Untested thread schedules, Classic endpoint lifetime and
asynchronous originating-session propagation retain the limits stated above.

The full two-profile [mandatory matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37683307104)
is still pending. Source/documentation CI passed at the tested source. No merge,
release, desktop pin or installed GUI adoption is claimed by this checkpoint.
Raw build and guest evidence remains in the operator's private evidence archive.
