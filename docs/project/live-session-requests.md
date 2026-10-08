<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Fixed userspace requests for live LPF2 experiments

The simulation-only `port simulation-session-request OPERATION` command exposes
bounded actual userspace calls on port F. It is compiled only when protected
build, LUMP and the TI-free simulation selection are all enabled. It is a test
interface, not a program SDK or a motor authority interface.

The command opens F read-only, performs at most six nonblocking poll ioctls,
publishes bounded observations and closes its descriptor. It also attempts
text replies through its normal standard output. A batch keeps that one
exclusive descriptor throughout. It accepts no caller-supplied address, ioctl
number, queue write, counter value or monitor command. Invalid, missing or
32-byte-or-longer operation names are rejected before opening a port.

| Operation | Actual request | Reply bytes |
| --- | --- | --- |
| `poll` | Session-bearing DATA poll | All 48 output bytes |
| `legacy` | Legacy DATA poll, sharing the same queue | All 36 output bytes |
| `null` | Session poll with null output | None |
| `readonly` | Session poll with the existing user-flash test object | None |
| `kernel` | Session poll with the fixed kernel-RAM test address | None |
| `wrap` | Session poll with the fixed wrapping test range | None |
| `legacy-tail` | Session poll with only 36 bytes left in user RAM | None |
| `invalid-then-poll` | The five refusals above, then one valid session poll | Last request's 48 bytes |

The invalid addresses are the existing protected refusal probe's fixed test
cases. Valid output is filled with `a5` before the syscall. On the ARM target,
the session ABI is little-endian: an eight-byte session, the 36-byte legacy frame
and four reserved bytes. A successful session must come from the guest; the host
does not seed or repair it. Errors and untouched bytes remain observable.

When standard output is connected, each reply is a complete ASCII line:

```text
BW_LUMP_REQUEST v=1 op=OPERATION step=N rc=RESULT errno=ERROR bytes=HEX_OR_DASH
BW_LUMP_REQUEST_END v=1 op=OPERATION calls=N close_rc=RESULT close_errno=ERROR
```

Reply bytes are lowercase hex of the exact fixed-size buffer; invalid-pointer
requests use `-`. An open failure emits only `BW_LUMP_REQUEST_OPEN v=1 op=OPERATION rc=-1 errno=ERROR`
and exits with failure, without issuing a poll. It has no completion/end line.
The end line is emitted after descriptor close. Return code zero
means the diagnostic completed and closed its descriptor, even if a poll returned
an error. It is not a PASS verdict. The external fixture must check every syscall
result, errno, output byte, ordering and final close before declaring a result.

## Qualification contract

`python3 tools/test_lump_requests.py` compiles the actual request core with syscall
doubles. Nineteen baseline invocations cover rejected input before I/O, open and
close failures, legacy/session output, empty buffers, the five fixed faults and a
successful synthetic batch and silent startup. Three compiled mutations test lost errno, a close
between batch requests and accidental console output from startup. These are host controls, not kernel or ARM results.

The existing ordinary-simulation startup invokes the original refusal diagnostic,
then the new batch with text output disabled so an unattached USB console cannot
block the diagnostic. The interactive command retains its text replies. The enhanced `simulation/renode/lump-probe.robot` reads the
ELF-resolved `g_bw_lump_request` publication through the bounded, read-only
`simulation/renode/lump_requests.py` observer. The 400-byte version-one record
contains sequence, operation selector, open/close results and six ordered
60-byte syscall records (result, saved errno, length and 48 output bytes).
State 1 is running, 2 is completed including syscall errors, and 3 is open failure.
The observer requires the complete startup sequence 1, stable state/sequence,
correct ELF RAM extent and every expected result and output byte. It has no
write interface. Host controls reject corrupted fields, ranges, state and timeouts.

The configured console is USB CDC, while USART2 is Bluetooth HCI. A cancelled
queued prototype run targeted the wrong UART and did not execute the guest;
its source is retained in history. This fixture qualifies guest publications,
not UART replies or interactive USB transport.
The inactive expected results are EINVAL for null, EFAULT for the other four,
then EAGAIN with all 48 sentinel bytes unchanged. HCI compiles the command but
does not run this startup diagnostic.

The startup-only request core was qualified at source
`25e29ebac0ad84829b909664dcc92e9037c08d5d` in
[two-profile matrix 37791490061](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37791490061)
and merged in [PR #45](https://github.com/CrispStrobe/brickwright-spike-prime-fw/pull/45).
Both protected profiles passed their compiler, linker, notice, resource and
TI-exclusion gates. Each used 597580 of 654336 userspace flash bytes and 89280
of 98304 static RAM bytes; TI hits were zero. Their 24976-byte probe objects
matched SHA256 `11cfd83757900eab821360ac7b7a83c245b1dd85db70a04bb52f2637f60901f1`.
The ordinary profile passed the original refusal diagnostic, six-call startup
publication and retained program/storage regressions. All seven HCI peer reports
passed. This qualifies inactive startup observations only; later mailbox or
active-session changes require their own affected guest qualification.

## Next live-session fixture

The inactive startup qualification above is complete. Next prove an external
caller can invoke the fixed operations through
the real console/program transport with normal services running; startup entry
alone does not qualify interactive upload or cancellation.

Use the already qualified external DATA-budget model interface to deliver a
bounded, distinct frame to a genuinely synchronized F. Preserve raw UART and
budget observations; do not write engine queues, session counters or guest RAM.
Run the invalid-then-poll batch with one known queued frame and require the valid
poll to return that same frame and a nonzero guest session. Check subsequent
empty polls, shared legacy consumption, detach/reset and same-type replacement.
Any competing consumer, resynchronization or watchdog expiry must be recorded;
it cannot be treated as proof of invalid-call non-consumption.

Active DATA consumption, reset identities, readiness waiting, conditional PWM
admission, installed GUI adoption and physical fidelity remain outside the
inactive fixture. Keep application images, raw execution receipts and machine
locations private. Retained firmware attribution and obligations remain; these
new diagnostic components use BSD-3-Clause without a whole-firmware independence
claim.

A separate [diagnostic mailbox candidate](live-session-mailbox.md) connects these
fixed operations to the existing guest worker without USB-console assumptions.
Its transport, exhaustion and concurrency controls require their own fresh guest
qualification; they do not extend the earlier startup-only evidence.
