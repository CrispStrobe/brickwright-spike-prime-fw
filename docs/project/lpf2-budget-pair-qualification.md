<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# External LPF2 DATA budget pair qualification

This candidate explicitly changes the test Runtime/Infrastructure pins from
`756b684eee56ba698a931a14b3f4885cb8d8ada6` /
`fe4ad383c7392527433783fcec455daa7ddc2bb7` to
`8f7696aac606d8de90c1a6a0930e48655f03530a` /
`1253d925accca23dfda66d5bca61e78498dcb64f`.
The pair is recorded in [Runtime PR #54](https://github.com/CrispStrobe/renode-spike-prime/pull/54)
and [Infrastructure PR #36](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/36).
No guest firmware compiler input, configuration, physical target or installed
desktop consumer pin changes. The affected NuttX guest matrix passed for this pair;
the separate upstream-MicroPython application qualification remains pending.

The existing source-built Runtime installer still verifies the exact gitlink,
all submodules and support-library pins before compiling. Its build receipts
retain both revisions and native/managed output hashes. The Bluetooth-air tree
and all six recorded source-file hashes are identical to the prior reviewed
inputs. Package versions, installed notice hashes and requirements stay unchanged;
only the matching Runtime source identity in that host-input record changes.
This is not a new whole-distribution provenance or licence-clearance claim.

[The model run](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37764701627)
passed at this exact pair, including eighteen budget cases and three compiled
model mutations. The full peripheral suite reported 584 passed and five skipped
cases. A separate host-observer race fix in Infrastructure changes test code and
documentation only; this qualification deliberately retains the immutable
model-tested pair above.

## Actual affected guest qualification

[Run 37775158539](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37775158539)
passed both profiles at firmware source
`3238f2ba9d0e2f5574ad86c1a4672693353a358b`, with the exact pair above. Both
passed compiler/linker/notice/resource/TI gates. Ordinary simulation passed
protected boot, the protected-userspace syscall refusal probe, retained program
restarts, interrupted storage and the source-generated empty filesystem seed.
HCI passed its transport bridge and all seven complete air reports: LE,
Scratch Link, IMU acquisition, stationary samples, poses, calibration and Classic
motors. The seven reports identify the same four firmware files and the expected
Runtime revision. The report verifier also rejected missing-report,
conflicting-image and wrong-Runtime negative controls. These controls test the
verifier; they are separate from the three compiled model mutations.

Both profiles measured userspace flash 596,508/654,336 bytes, static RAM
88,880/98,304 bytes and zero TI payload. Both compiled the 13,312-byte refusal
probe object with SHA256
`ab5cda6b09be02714418d5d67bf0c28ba30a9bd84c094a08948a49c4fa6e1dcd`.
The dedicated refusal probe ran only in ordinary simulation, not HCI. These
measurements do not establish kernel heap usage or physical-device safety.

The earlier failures remain recorded separately. Raw logs and derived receipts
are retained privately. This later documentation update changes no compiled
source, guest configuration or dependency pin; it does not require another
unchanged ARM matrix.

The earlier [protected refusal qualification](lump-guest-probe.md) consumed the
previous pair and remains separate evidence. This replacement matrix
qualifies only its observed regressions; it does not establish active-session DATA
polls, invalid-call non-consumption, reset identities, atomic PWM admission,
physical fidelity or stock/reference firmware boot. Separately supplied upstream
MicroPython application execution also needs its own candidate qualification
before adopting the revised offline support source profile.
