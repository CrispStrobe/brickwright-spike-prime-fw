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

## Fresh candidate results

Tested firmware and harness source:
`95ea0d44c9da3e1956e74466c4071f91254751f4`. Both clean protected profiles
passed compiler-input, linker, configuration, notice, resource and local
TI-exclusion gates. Simulation used 594,888/654,336 bytes of userspace flash;
simulation-hci used 594,880/654,336. Both used 88,600/98,304 bytes of userspace
static RAM and zero TI payload bytes. Host link controls also passed under
AddressSanitizer and UndefinedBehaviorSanitizer.

Fresh local qualification used compiled Runtime source
`8f128e66d0be5f83da035eaba9cc4441c0a29a31` and Infrastructure source
`adf40d98062a6b31aae7ef86e1ae5f289eebdc48`, without source model extensions.
These are separate from the firmware matrix's retained dependency pins.
The simulation image passed the six-port native/Python scenario with 208
observations: speed and position commands, concurrent motors, cancellation,
drive release and execution beyond the reset regression boundary. Six position
endpoints had maximum error 1.571 degrees against the 3-degree tolerance.

The simulation-hci image passed Classic signed motion, concurrent commands,
cancellation and load timeout. Its attachment-change scenario reported
`-ENODEV`, guest type transitions 14→0→14 and counters 1→2→3, released drive,
and fresh -90-degree motion measuring -94.087 degrees within the 20-degree
tolerance. The first attempt correctly refused an old-kernel diagnostic layout
before guest startup. Regenerating the read-only layout from our new kernel ELF
enabled the rerun; the original refusal remains preserved.

The combined scenario passed with authenticated/encrypted Classic alongside
subscribed BLE. A/B moved +367.856/-367.509 degrees for ±360-degree requests,
within the 20-degree tolerance. Three initial 1000 mm records were followed by
three exact 250 mm records while read-only observations showed opposite powered
motion. Terminal replies, duplicate-reply quiet checks, unsubscribe,
resubscription and a fresh central passed. Thirty-six guest-clock observations
completed without error. The fields are sequential observations, not an atomic
electrical sample or physical SPIKE measurement.

The [mandatory matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37662520208)
tests the same firmware source with its retained pins. Both jobs passed,
including the official TI fingerprint checks and all seven Bluetooth air modes:
LE, Scratch Link, Classic, stationary IMU, poses, calibration and measured motors.
The final documentation changes no firmware source or dependency pins.
These finite results do not qualify desktop adoption, all session races,
terminal delivery under saturation or physical hardware behavior. Raw logs and
failed harness attempts remain private. Remaining implementation work has
[separate lane contracts](tx-followup-lanes.md).
