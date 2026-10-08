<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# HCI stream lifecycle adoption candidate

The qualified [active F matrix](active-session-qualification.md) retains an HCI
helper background connection-reset diagnostic after a passing peer report.
This candidate tests [Runtime PR #55](https://github.com/CrispStrobe/renode-spike-prime/pull/55),
source `b34becc947ac9c998881bb018dfe2cec4b1398b2`, before adopting its stream
task ownership and error preservation. Runtime checks pass; the HCI part of
affected firmware qualification is still pending.

Infrastructure remains `1253d925accca23dfda66d5bca61e78498dcb64f`. Relative to the
previous consumed Runtime `8f7696aac606d8de90c1a6a0930e48655f03530a`, no compiled
peripheral model or native translator source changes. Runtime main's intervening
qualification documentation remains separate from this helper fix. Firmware
C/configuration inputs and host package versions/notice hashes are unchanged.
The installer and host-air inventory bind the exact Runtime and nine tracked
air files, including retained/new licence text and the lifecycle contract.

The Runtime helper's [contract](https://github.com/CrispStrobe/renode-spike-prime/blob/b34becc947ac9c998881bb018dfe2cec4b1398b2/tools/bw-air/STREAM-LIFECYCLE.md)
defines EOF/removal, owned task joins, abandoned data, observable read/write
failures, secondary close diagnostics and cooperative deadlines. Seventeen
synthetic-I/O controls and two actual-source mutation controls pass locally;
these do not qualify actual firmware or network teardown. Hosted real TCP/Bumble
HCI Reset/EOF, LE and Classic smoke and all enabled Runtime checks remain gates.

Run the existing two-profile firmware matrix on this candidate. Require every
mandatory compiler/link/notice/resource/TI gate, ordinary protected worker and
active F experiment, retained program/storage regressions, and all seven HCI
peer reports. Audit common four-image identity and this exact new Runtime across
all reports. Preserve original logs, including failures and any background
errors; do not normalize them away or treat a peer PASS as clean helper teardown.
Report explicit failures or abandoned/close diagnostics separately. This does
not prove physical radio, whole-AirLink/process lifecycle, GUI adoption or
bounded queue/backpressure. No reference image is needed, fetched or inspected.

After Runtime checks, affected actual guest qualification and final-head firmware
CI pass, record exact tested/final heads and merge-tree equality before normal
own-fork adoption. Until then keep the existing qualified main and its immutable
pins as the baseline; do not describe this branch as shipped.

## Completed Runtime and ordinary guest checks

At exact Runtime source `b34becc947ac9c998881bb018dfe2cec4b1398b2`, the
[hosted lifecycle job](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37826093042)
passes seventeen synthetic-I/O controls, both assertion-detected source mutants,
real TCP/Bumble HCI Reset and joined EOF, LE GATT and Classic pairing/encryption/
L2CAP smoke. [Runtime CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37826093037)
passes all enabled steps, including 466 focused model tests and the full
peripheral suite with 584 passed and 5 skipped. There are no skipped job steps;
the five are individual test cases. Raw logs are preserved privately.

Firmware source `18b64e8f4d1c772ed4e2800a36cd591fbe0523aa` is under test in
[matrix 37826405416](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37826405416).
The ordinary profile completed successfully; the HCI profile is still pending.
Whole-matrix and helper-diagnostic qualification are not yet claimed. Both
[firmware source/documentation checks](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37826408753)
pass at that exact candidate.
