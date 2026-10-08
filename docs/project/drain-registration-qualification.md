<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Drain registration identity candidate

This implements the TX drain API part of [T03](tx-followup-lanes.md).
The application currently has no production caller registering a TX drain
wait: the callers found are host tests. Do not describe this as a demonstrated
production timer failure or as an installed GUI feature. Classic connection
lifetime and asynchronous reply admission remain separate lanes.

## Contract

The owner is `apps/btsensor/btsensor_tx.c`; its public declarations are in
`apps/btsensor/btsensor_tx.h`. This internal API intentionally changes: callers
must supply identities to expiry/cancellation and handle one terminal callback
with an explicit result. There is no identity-free expiry compatibility path.

- `set_timer_ops(start, cancel, context)` installs a provider. Supply both
  functions or neither (`-EINVAL` otherwise). Replacement returns `-EBUSY`
  while any drain registration, installed timer or timer operation owns it.
- `arm_post_drain_callback(callback, context, timeout_ms, &identity)` admits
  one wait. Milliseconds use an unsigned 32-bit value; zero requests no timer.
  Empty queues complete immediately without starting a timer. The identity is
  written before any callback, even if completion is synchronous.
- Admission returns zero; a callback may already have run. Negative returns
  mean no admission: `-EINVAL` for missing callback/output pointer, `-EBUSY`
  for an existing wait, `-ENOTSUP` for a needed missing provider, and
  `-EOVERFLOW` when the process-lifetime 64-bit counter is exhausted. A valid
  output pointer is set to zero on failure. Init/deinit never reset the counter.
- The terminal callback receives its identity and either zero for empty local
  queues, `-ETIMEDOUT`, or a negative provider-start error. Empty queues do not
  prove remote receipt or physical delivery. A registration has at most one
  terminal callback; start failure cannot remove a replacement wait.
- `clear_post_drain_callback(identity)` returns true if cancellation won. It
  then prevents a callback from claiming that identity. False includes stale
  identities and callbacks already claimed; it is not a callback join. Keep
  callback context alive until cancellation wins or its callback returns.
- Init/deinit and disconnect/selection changes that discard queued output
  cancel the current wait without a terminal callback. An unrelated empty link
  cannot cancel it. Lifecycle calls do not join already claimed callbacks.
- Expiry carries the original identity and acts only on the matching active,
  installed timer. Old, duplicate, zero and untimed-registration expiry calls
  have no effect on a replacement wait.

A single reconciler serializes provider start/cancel operations outside the
queue mutex. Reentrant/concurrent calls update desired state; they do not start
nested provider operations. Cancellation of an old installed timer finishes
before a replacement is started. Provider functions must return promptly, may
reenter this API, and return zero or negative errno for start. A failed start
must leave no timer armed. Cancellation may leave an already queued expiry;
that expiry must retain its old identity. Provider/context ownership lasts
through its operation; replacement is allowed only when `set_timer_ops`
succeeds. Callback functions also run outside the queue mutex.

`timeout_ms` is passed unchanged to the provider when its serialized start
executes. It is a delay from provider start, not an absolute admission deadline.
The API adds neither a wall clock nor real-time pacing. A future production
provider must qualify its own simulated-clock semantics and bounded operation
latency; these host controls do not establish that integration.

## Reproducible controls and qualification boundary

```sh
tools/check_btsensor_tx_drain.sh
python3 tools/prove_btsensor_tx_drain_mutations.py
tools/check_btsensor_tx.sh
tools/check_btsensor_tx_links.sh
python3 tools/prove_ble_session_mutations.py
python3 tools/prove_btsensor_tx_links_mutations.py
```

The new controls compile the actual TX module with a neutral timer/transport
boundary. They cover old expiry/cancel after replacement, duplicate expiry,
replacement inside start/cancel/completion callbacks, lifecycle reset during
start, drain versus expiry, failed old start after replacement, disconnect,
missing/busy providers, untimed waits, maximum 32-bit delay passthrough and
synthetic identity exhaustion. A real
pthread/condition-variable schedule blocks a start while another thread cancels
and registers a replacement. Each executable has a ten-second wall bound.

Five compiled mutations must fail assertions: accept stale expiry, accept stale
cancellation, overlap provider operations, reuse identities after init, and
let an old start failure clear a replacement. Compiler failure is not detection.
The previously reproduced identity-free API failure remains preserved privately.

Only the two changed TX source/header hashes are refreshed in each protected
compiler-input inventory. Retained Apache-2.0 implementation and inherited MIT
header selections and notices remain intact. New test/tool/documentation
components use BSD-3-Clause. This is not a whole-firmware independence or licence
clearance claim.

## Candidate qualification record

Tested source: `a2dbe8b75db1b58872f161488a951f9475d4f2ec`.
[Source and documentation CI](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37703135304)
and the [complete protected matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37703134582)
passed. Both clean ARM profiles passed compiler-input, linker, resource and
zero-TI-payload gates, including the official 40-chunk fingerprint control.
The HCI job executed all seven air modes; the non-HCI job executed protected
boot, retained program restarts, interrupted program storage and empty-seed
checks. Profile-inapplicable steps were skipped, not credited as executed twice.

Clean candidate resource measurements were 595876 flash bytes for `simulation`
and 595892 for `simulation-hci`, against 654336; both used 88848 RAM bytes
against 98304. Local host controls also passed AddressSanitizer and
UndefinedBehaviorSanitizer. These are candidate measurements, not a desktop
package adoption record.

Additional local compiled-Renode qualification remains blocked. The unchanged
Classic all-motor scenario twice returned `-EAGAIN` for the long degree move
used to test cancellation, before admitting motor motion; the probe then timed
out waiting for motion. In a matched baseline/candidate comparison, the older
`e6f10f9ae8e47ae070693e966e03a7b3d3e18d35` firmware passed and this candidate
failed. A second unchanged baseline run also passed. That local comparison
used Runtime
`8f128e66d0be5f83da035eaba9cc4441c0a29a31` and Infrastructure
`adf40d98062a6b31aae7ef86e1ae5f289eebdc48`, distinct from the workflow's
pinned matrix context. This does not establish causation or equivalence across
those contexts. Preserve the failure; the green matrix does not erase it.
Separate candidate detach/reconnect and overlapping BLE/Classic motor scenarios
passed in that local compiled context. They add bounded coverage and do not
resolve or replace the failed all-motor cancellation scenario.

The encoder backend deliberately refuses admission until a fresh matching UART
frame is available. Initial readiness does not guarantee a fresh frame for a
later command. See [T04](tx-followup-lanes.md#degree-readiness)
for the unresolved sequencing contract. Do not weaken movement, cancellation,
reply or timing assertions to turn the original failed scenario into a pass.
Two earlier local attempts failed before guest execution because the host
configuration/history destination was not writable; those are environment
failures, separately retained from the observed command refusal.

Keep this candidate unmerged until the local comparison boundary is resolved.
Host controls alone do not authorize merging firmware. No desktop pin, package
or installed GUI adoption is included. Direct production timer/guest scheduling
qualification remains a future task until an actual application caller is added.

## Pending inactive-timer fast-path comparison

A follow-up avoids entering the timer reconciler when the locked state has
neither an installed timer nor a timed registration. An already running
reconciler remains responsible for concurrent desired-state changes. This
removes an unnecessary mutex round trip from ordinary transport pumps where
no drain timer is registered; it does not change encoder admission or add
host retries. Existing threaded/reentrant drain controls, five targeted
mutations, transport controls and sanitizers passed locally for this change.
Fresh clean ARM builds, the mandatory matrix and unchanged compiled guest
comparisons are pending. The earlier source-specific results above do not
qualify this follow-up, and the local failures remain preserved. No causal
explanation or merge clearance is claimed from the host controls.
