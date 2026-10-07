<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# BLE and Classic transmit destination qualification

The simultaneous-link diagnostic exposed modern notification bytes on Classic
after that connection supplied incoming traffic. The first diagnostic also used
invalid five-character request IDs. The corrected four-character-ID baseline
received a motor reply but still failed when redirected binary notifications
reached the Classic text parser. Both failures remain preserved. They are not
simultaneous-motion qualification.

The candidate binds each queued response/frame to its destination and the TX
connection-state generation at admission. Receive-side selection changes only
the compatibility default. Modern messages explicitly target BLE; Classic JSON
and neutral command replies target their originating link; legacy bundle frames
explicitly target Classic. Pending entries keep their destination under
back-pressure. A blocked destination does not prevent the other link progressing.
Connection-state disconnect or generation change discards that link's queued
entries without discarding the other link's work. Unique queue tickets prevent
completion of an old send from consuming a replacement occupying the same slot.

Capacity stays bounded: the frame queue retains its configured depth minus one
usable entries, and responses retain three usable entries. Responses precede
telemetry among destinations that can currently send; FIFO order is retained
within each queue. Full telemetry replaces the oldest entry and returns
`-ENOSPC`; full responses refuse admission. Explicit-link enqueue without an
admitted link returns `-ENOTCONN`. Receive-side link changes no longer retarget
already queued entries. Callback reentry is coalesced into at most one immediate
retry per pump invocation, preserving a finite refusal bound.

Response priority refers to the response enqueue API. Classic JSON currently
uses the frame queue, so its terminal replies are not guaranteed admission
under frame-queue saturation. This remains a separate delivery limitation.

Reproducible host controls:

```sh
tools/check_btsensor_tx.sh
tools/check_btsensor_tx_links.sh
python3 tools/prove_btsensor_tx_links_mutations.py
tools/check_btsensor_commands.sh
tools/check_btsensor_classic.sh
tools/check_btsensor_neutral_compile.sh
```

The new controls exercise alternating selection, independent back-pressure,
response priority, disconnect/reconnect, generation changes, replacement during
a send callback, and can-send reentry. Two source-compiled mutations are
required to fail the external comparisons: redirect a tagged send to the
selected link, or retain a queued response from an old session. Compilation
failure is not accepted as mutation detection. The mutation runner has a
ten-second bound per executable and disables core dumps.

These controls do not certify an atomic final handoff to a changing transport
connection. The underlying send API currently accepts a link rather than an
explicit session token. Likewise an asynchronous producer must retain its
originating session token to close a completion/reconnect admission race;
queue-time generation capture alone is insufficient. Post-drain timer callback
identity and cancellation races are separate retained limitations. Do not claim
all session races are solved by these queue tags.

Clean protected ARM builds, compiler/linker/input/resource/TI-exclusion checks
and actual guest single-link plus concurrent qualification are required after
this source change. A private candidate build is not release qualification and
does not waive official TI fingerprint revalidation or the mandatory matrix.
The transport API's existing all-or-error send contract is retained; no new
partial-byte acceptance or arbitrary oversized-frame guarantee is asserted.

The first private candidate build stopped before compilation because the
reviewed input inventories retained old hashes for the changed TX implementation,
header and neutral reply adapter. Those three entries are refreshed for both
profiles, preserving their existing Apache-2.0 and inherited MIT selections.
No configuration, compiler runtime, dependency pin, linker-member expectation
or notice selection is relaxed. The subsequent build must verify the actual
compiler closure and linker selections; refreshing hashes is not a build pass.
