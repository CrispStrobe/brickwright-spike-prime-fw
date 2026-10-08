<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Simulation-only session request transport

This extends the [fixed request core](live-session-requests.md) with an explicit
diagnostic mailbox. The inactive protected-guest transport and host controls
passed the qualification below. It prepares live LPF2 experiments.
It does not implement USB, BLE or a public program SDK.

The existing hubprogram worker services requests before taking its application
mutex, and its embedded-Python poll hook also services them before that mutex.
No new daemon, heap allocation, cached sensor state or guest result injection is
introduced. The build flag requires the TI-free simulation profile, protected
build, LUMP and the port application together. Hardware and ordinary host builds
omit the integration. An uncooperative Python program can delay its poll hook;
this is not a universal response-time guarantee.

## Ownership and wire contract

Resolve `g_bw_lump_request_mailbox` and `g_bw_lump_request` from the actual guest
ELF. Validate their full 32-byte and 400-byte extents in userspace static RAM,
require non-overlap and paused emulation before submitting a request. Exactly
one host coordinator may use a mailbox. The separately published syscall result
remains guest-owned; the host never writes it or any queue/session counter.

All mailbox words are 32-bit little-endian:

| Offset | Owner | Field |
| --- | --- | --- |
| 0 | Host | Request magic `0x42574c52` |
| 4 | Host | Request version, currently 1 |
| 8 | Host | Nonzero request sequence, committed last |
| 12 | Host | Fixed operation selector |
| 16 | Guest | Completed reply sequence; zero while processing, committed last |
| 20 | Guest | Signed transport result |
| 24 | Guest | Correlated guest publication sequence, or zero if no core call ran |
| 28 | Guest | Echoed operation selector |

Selectors 0–7 are respectively `poll`, `legacy`, `null`, `readonly`, `kernel`,
`wrap`, `legacy-tail`, `invalid-then-poll`. The host request sequence is only transport correlation; it is not a UART
synchronization identity. These selectors accept no address, ioctl number,
frame payload, expected UART identity or arbitrary command string. The service
uses the same real open/ioctl/close core as the CLI, with text output disabled.

Begin at sequence 1 and increment by one after each completed reply. Zero is
idle. Duplicate or older requests never execute again or alter the last reply.
A newer malformed request (including a sequence gap, wrong magic/version or
unknown selector) completes with `-EINVAL` and no core call; that sequence is
consumed, so a caller can recover using its successor. The host adapter itself
refuses pending replacements, invalid selectors and sequence exhaustion before
writing any word. After `UINT32_MAX`, reboot is required; neither request nor
publication identity wraps. Discard all handles on reset or emulator replacement.
Cross-reset stale-handle detection is not supplied by this version-one ABI.

Transport result zero means the bounded diagnostic completed and closed its
port, including a poll returning `EAGAIN` or `EFAULT`. It is not a syscall PASS.
Open/close failure returns its negative errno; an anomalous failure with errno
zero returns `-EIO`, while preserving that anomaly in the publication. A
competing request core returns `-EBUSY` without changing the current publication.
Publication exhaustion returns `-EOVERFLOW` without I/O. Internal admission
locks prevent concurrent service/CLI calls from replacing an in-progress core.

The guest invalidates the old reply sequence to zero before processing a newer
request, so an old ordinal cannot attest partially replaced response fields.
Read request and reply sequence before and after the response words; require the
expected sequence and selector. The adapter rejects handles once a newer request
has been submitted, even if its reply has not yet completed. Then read the guest publication with stable state and
sequence and require the reply's publication identity. Another CLI diagnostic
can overwrite a completed publication; the adapter rejects the stale handle
rather than attributing its replacement to the old request. Poll and batch
results still require exact external scenario comparisons.

The adapter checks a one-simulated-second limit and a 30-host-second deadline
between synchronous `RunFor` calls. The clock check cannot interrupt a stalled
`RunFor`; the enclosing Robot test separately declares a 600-second timeout.
These cooperative checks are not a hard process-supervision or teardown claim.
Timeout is not cancellation or permission to edit reply
words: the request remains outstanding. Continue observing it, or explicitly
reset the owned simulated machine and discard its handles. There is no separate
cancellation opcode for these bounded, read-only diagnostics. Existing program
Stop and motor ownership contracts are unchanged.

## Reproducible controls and actual guest gate

```sh
python3 tools/test_lump_requests.py
python3 tools/test_lump_mailbox.py
python3 tools/test_lump_request_transport.py
```

The first command retains nineteen request-core scenarios and three compiled
mutations. The mailbox C controls exercise duplicates, malformed input, gap
recovery, legacy/batch calls, busy ownership, open/close errors including missing
errno, and both sequence-exhaustion boundaries. Four rebuilt C mutations must
fail assertions: repeated admission, leaving the old reply live, ignored version
and ignored core ownership.
Ten host adapter/bridge tests cover the exact writable extent/commit order, pending and
exhausted requests, stale/mismatched/changed replies, output bytes and changed
publications. Bridge controls exercise paused-state admission, both cooperative
deadlines, scheduling and exact correlated output against a synthetic host worker.
They do not execute Renode or the actual worker loop. Sixteen actual Make selections verify the integration build guard.
The existing program-service host controls also run with the diagnostic flag.
These are host tests with syscall doubles, not kernel or ARM execution.

The extended `simulation/renode/lump-probe.robot` first preserves both previous
startup checks, advances an explicit 20 ms scheduling interval, then submits
batch/session/legacy operations through the real worker. It requires all three
sequence-correlated actual protected-guest replies, exact refusal errors,
unchanged sentinel output and successful descriptor close. Fresh clean builds of
both simulation profiles and all compiler/link/notice/resource/TI/guest gates are
required before adoption.

### Completed inactive guest qualification

Source `95a24712f1875bb12e1ec1125373fa5335c23675` passed
[two-profile matrix 37795457573](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37795457573).
The ordinary profile passed the original refusal probe and startup batch, then
all three sequence-correlated mailbox roundtrips through the real protected
program worker. It also passed retained program restarts and storage regressions.
HCI compiled the same diagnostic object, omitted the inactive guest test, and
passed all seven Bluetooth-air peer reports. Those reports identify the same
four firmware files and Runtime `8f7696aac606d8de90c1a6a0930e48655f03530a`.
The report verifier rejected missing-report, conflicting-image and wrong-Runtime
negative controls; those are verifier controls, separate from compiled C mutations.

Both profiles passed compiler, linker, notice, resource and TI-exclusion gates.
Ordinary simulation used 597892 of 654336 userspace flash bytes; HCI used 597908.
Both used 89320 of 98304 static RAM bytes and contained zero TI payload. Both
28236-byte probe objects matched SHA256
`d8aad74de697747a89b5692789310669d9cf75357a6992bf8d711648750a8f92`.
These static measurements do not establish stack/heap high-water marks.
Subsequent baseline-merge and qualification-documentation changes leave the
compiler, configuration, dependency, Robot and transport inputs unchanged.
Raw logs and receipts are retained privately. This result qualifies the inactive
worker request path, not active DATA, USB/BLE upload, cross-reset identities,
embedded-Python poll-hook scheduling under a running program or GUI adoption.

Next synchronize a genuinely attached F and
use the qualified model's bounded external DATA emission control. Check distinct
frame survival across invalid calls, shared legacy consumption, empty polls,
session loss, same-type replacement and per-port isolation. Any competing
consumer, watchdog expiry or resynchronization remains an observed limitation;
do not manufacture evidence by writing queues, identities, completions or PWM.
Active DATA, transport reset identity, conditional motor admission, installed
GUI adoption and physical fidelity remain separate tasks.

New diagnostic components use BSD-3-Clause. Retained firmware/dependency
attribution and obligations remain; no whole-firmware independence claim follows.

The next [active F experiment](active-session-qualification.md) has separate
controls and guest gates; its candidate status does not broaden this result.
