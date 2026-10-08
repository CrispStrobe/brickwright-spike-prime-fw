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
desktop consumer pin changes. Test guest execution is pending for this pair.

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

Run the existing `Firmware build and simulation` workflow at the exact candidate
source. Both profiles must pass compiler/linker/notice/resource/TI gates; ordinary
simulation must pass protected boot, syscall refusals, retained program restarts
and storage checks. HCI must pass its transport bridge and all seven air peers with
a common four-file firmware identity. Preserve original failures and raw logs
privately. Do not repeat an unchanged successful matrix for later prose updates.

The earlier [protected refusal qualification](lump-guest-probe.md) consumed the
previous pair and remains separate evidence. A passing replacement matrix would
qualify only its observed regressions; it would not establish active-session DATA
polls, invalid-call non-consumption, reset identities, atomic PWM admission,
physical fidelity or stock/reference firmware boot. Separately supplied upstream
MicroPython application execution also needs its own candidate qualification
before adopting the revised offline support source profile.
