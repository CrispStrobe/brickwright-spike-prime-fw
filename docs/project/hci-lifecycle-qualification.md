<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# HCI stream lifecycle qualification

The earlier [active F matrix](active-session-qualification.md) retained an HCI
helper background connection-reset diagnostic after a passing peer report.
[Runtime PR #55](https://github.com/CrispStrobe/renode-spike-prime/pull/55), tested
source `b34becc947ac9c998881bb018dfe2cec4b1398b2`, adds stream task ownership,
joined shutdown and error preservation. Both Runtime checks and the affected
complete firmware matrix now pass. This record describes finite simulation
qualification, not all transport or physical behaviour.

## Exact inputs and contract

Infrastructure remains `1253d925accca23dfda66d5bca61e78498dcb64f`. Relative to the
previous consumed Runtime `8f7696aac606d8de90c1a6a0930e48655f03530a`, no compiled
peripheral model or native translator source changes. Runtime main's intervening
qualification documentation remains separate from this helper fix. Firmware
C/configuration inputs and host package versions/notice hashes are unchanged.
The installer and host-air inventory bind the exact Runtime and nine tracked
air files, including retained/new licence text and the lifecycle contract.

The helper's [contract](https://github.com/CrispStrobe/renode-spike-prime/blob/b34becc947ac9c998881bb018dfe2cec4b1398b2/tools/bw-air/STREAM-LIFECYCLE.md)
defines EOF/removal, owned task joins, abandoned data, observable read/write
failures, secondary close diagnostics and cooperative deadlines. Retained
Apache-2.0 notices and newly authored BSD-3-Clause controls remain distinct.
No whole-firmware independence or release-wide licence claim follows.

## Completed Runtime checks

At exact Runtime source `b34becc947ac9c998881bb018dfe2cec4b1398b2`, the
[hosted lifecycle job](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37826093042)
passes seventeen synthetic-I/O controls, both assertion-detected source mutants,
real TCP/Bumble HCI Reset and joined EOF, LE GATT and Classic pairing/encryption/
L2CAP smoke. [Runtime CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37826093037)
passes all enabled steps, including 466 focused model tests and the full
peripheral suite with 584 passed and 5 skipped. There are no skipped job steps;
the five are individual test cases. Raw logs are preserved privately.

## Complete protected-firmware qualification

Firmware source `18b64e8f4d1c772ed4e2800a36cd591fbe0523aa` passes
[matrix 37826405416](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37826405416).
The strict audit requires both clean profiles, every applicable mandatory step
and only the declared profile-specific skips. Compiler, linker, attribution,
resource and TI gates pass, along with ordinary protected worker/active F DATA,
retained program and storage regressions and all seven HCI peer reports.
All reports identify the same four firmware files and the exact new Runtime.
The report verifier rejects missing-report, conflicting-image and wrong-Runtime
negative controls. The ordinary F fixture again observes eight requests, five
external reports, sessions 1 to 2 and 790 simulated milliseconds to invalidation.

Both profiles measure 597,908/654,336 bytes of userspace flash and
89,320/98,304 bytes of static RAM, with zero TI payload. Their identical
28,236-byte probe objects have SHA256
`d8aad74de697747a89b5692789310669d9cf75357a6992bf8d711648750a8f92`.
These are static measurements, not heap/stack high-water marks.

The new HCI raw log has no matching unretrieved-task, delivery-failure,
writer-close, connection-reset or traceback diagnostic. That audit rejects
five synthetic failure-pattern controls and also detects the original defect
in the preserved earlier HCI log. One queued or indeterminate in-flight packet
is explicitly reported abandoned during shutdown. This is the documented abort
policy, not a flush or a guarantee that every emitted byte reached firmware.
Passing reports alone do not establish teardown correctness; report, job and
diagnostic audits remain separate evidence boundaries.

Both [firmware source/documentation checks](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37826408753)
pass at the tested source. Subsequent result/handover changes are Markdown only;
compiled firmware, configuration, Runtime pin, inventory and test inputs remain
unchanged. Require final documentation-head CI and reviewed/merge-tree equality
before normal own-fork adoption; do not rerun the unchanged ARM matrix for prose.

## Remaining work

This does not qualify bounded queue/backpressure, whole-AirLink or process
teardown, installed GUI adoption, physical radio or complete transport delivery.
No reference image is needed, fetched or inspected. The next bounded sensor task
is [two-port isolation](active-session-qualification.md#next-bounded-experiment-two-port-isolation),
with its own host adversaries and actual guest acceptance gates. Keep failures
and raw receipts private and preserve their original bytes.
