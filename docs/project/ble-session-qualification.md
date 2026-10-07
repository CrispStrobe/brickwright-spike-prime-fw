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

The TX queue drops an exact stale ticket without counting it as sent, blocking
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
initial condition, and independent Classic progress. Three compiled mutations
must fail assertions: ignore identity, omit the final reference, or recapture
the current identity at queue send. Compilation failure is not detection;
executables are bounded to ten seconds. These are host controls, not guest proof.

Both configured input inventories refresh only the three changed Apache-2.0
source/header hashes. Licence selections, notices, dependency pins, linker and
resource expectations remain intact. Fresh clean ARM builds, full mandatory
matrix/TI fingerprint checks, and compiled guest single-link/reconnect/overlap
qualification are still required before merge or package adoption.

Classic's mutable RFCOMM endpoint is unchanged and has no equivalent lifetime
guarantee. Asynchronous producers still need originating-session admission;
capturing the current session only when their completion enqueues is insufficient.
Terminal reply capacity, registration/callback ordering and drain/timer races
remain separate work. These finite controls establish neither physical safety,
whole-firmware independence nor general equivalence to another runtime.
