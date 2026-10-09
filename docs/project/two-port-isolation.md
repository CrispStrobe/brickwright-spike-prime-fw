<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# E/F sensor isolation experiment

This candidate extends the [F-only experiment](active-session-qualification.md)
and retains it as a regression. Host controls pass; actual protected-guest
qualification is pending. It does not yet establish E/F guest isolation.

## Fixed diagnostic interface

The simulation-only worker keeps its existing mailbox, sequence correlation,
publication and exclusive descriptor lifecycle. Selectors 0–7 retain their
existing F operations. Selector 8 (`poll-e`) opens `/dev/legoport4` and performs
one session poll; selector 9 (`invalid-then-poll-e`) keeps that descriptor open
across the five existing fixed invalid-pointer calls and a session poll.
Selectors 10 and higher are refused. F still opens `/dev/legoport5`.
Only the existing four request words are writable by the paused harness. No
user-selected ioctl, pointer, address, port path or executable input is admitted.
Output, sessions, DATA queues and UART/DCM state remain guest-owned.

The read-only own-kernel observer accepts an integer A–F index, validates the
same exact kernel hash, symbol, metadata extents and non-overlapping layout,
and checks the corresponding engine marker while paused. Index defaults to F
for existing callers. The actual new experiment selects E and F only. Host
index controls do not qualify other ports in an actual guest.

## External scenario and assertions

Both synthetic ultrasonic devices synchronize through normal model/guest UART
traffic with finite DATA budgets. All distances are synthetic millimetres.
Each initial admission must have the exact 36-byte frame, no drops, one queued
entry and its own nonzero session; continued-DATA windows track every appended
entry and later drain it in exact order. The original twelve-request/nine-report base sequence is retained. The continued
DATA revision adds two empty F polls and one poll per appended keepalive report:
`requests = 14 + keepaliveReports`, `externalReports = 9 + keepaliveReports`. It does not create concurrent program readers.

1. Queue F=1111 and E=2222. Read F, witness E's original pending payload/session,
   then read E. Queue F=3333 and E=4444 and reverse the read order.
2. Queue F=5555 and E=6666. Run E's five refused calls and its successful poll.
   Verify F remains pending. Empty-poll E with all 48 sentinel bytes unchanged
   and again verify F remains pending.
3. While bounded external F DATA continues, admit E=7777, detach E and witness
   actual inactive/empty E queue within five
   simulated seconds. Preserve F=5555/session before and after an empty E poll,
   then read F followed by all appended F reports in exact order. This checks
   that E teardown discards its admitted report while F continues receiving DATA.
4. With continued F DATA, reattach E, admit E=8888 and require its identity to
   increase within E. Drain every appended F report and verify E remains pending.
   Admit F=9999, read E and witness F unchanged, then read F. F's identity must
   remain its original live identity. Finish with unchanged empty polls on both.

Sessions need not differ numerically across ports. Only the replaced port's
identity must progress. Sensor bridge drive must remain zero when sampled;
this is an observation, not a physical safety guarantee. Existing one-second
request, 200-ms emission/admission and cooperative host deadline bounds remain.
RunFor cannot be interrupted by those cooperative checks. Robot retains its
600-second timeout; no new hard process or mailbox cancellation claim follows.

## DATA silence and bounded continued traffic

Before the pair experiment, a separate control attaches only F, admits one
12345-mm report and then withholds DATA. E stays detached throughout. Require
actual inactive/empty F queue within five simulated seconds while the model
remains Streaming, with unchanged model timeout/transmission counters, zero
DATA budget and zero drive. An actual unchanged empty poll follows, then F is
detached and the guest advances five seconds before the pair experiment. This
control is pending actual qualification; it does not retroactively establish
the cause of earlier failed experiments.

The pair experiment's continued-F-DATA feeder supplies distinct reports every
200 simulated milliseconds during E teardown and reattachment. Each window has
at most twelve extra reports, so an original front frame plus extras fits the
16-frame ring. Exhausting that cap fails explicitly even though the unchanged
five-second synchronization/teardown bounds are longer. This is a finite
roughly 2.4-second stimulus window, not a five-second traffic guarantee.

Every model emission must complete exactly one DATA budget/transmission and
produce an observed guest queue count increase with unchanged F session/front
and no drops. Partial snapshots are retried, not admitted as success. The feeder
advances only through normal guest time and never writes the queue, UART or
identity. After each window, settle all admitted reports, stop emission and
read the original followed by every known extra frame, with exact payload/order,
original session and an unchanged empty poll. Quiet drain is bounded to 400
simulated milliseconds from the last witnessed DATA admission, including steps
on the other port. No lost session is silently resumed. The second drain also
witnesses E's original pending payload/session after each F read.

This revises the external stimulus rather than firmware timeout behaviour. It
qualifies continued traffic only if actual execution passes; it does not claim
that a silent port must retain its DATA indefinitely.

## First actual guest result

[Matrix 37850880928](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37850880928)
at source `4132beeb31efa769fcf8b11131659e913c3ddbcd` fails the ordinary profile's
new experiment. The retained F-only scenario passes first; a subsequent F pending
payload/session witness reaches its guest deadline. The original message lacks
the expected distance/phase and does not identify which pending witness failed.
This is not evidence of successful E/F isolation or an established watchdog,
consumption or invalidation cause. Original raw logs remain preserved privately.
Source-policy and documentation CI pass at that exact source; they do not turn
the guest failure into qualification. The companion HCI result remains separate.

The first diagnostic follow-up adds a checkpoint label/request ordinal, expected distance/session and the observed queue plus
public model state, timeout/frame/budget/drive counters to that failure. A secondary
diagnostic-sampling exception preserves the original deadline message. It does
not change firmware, external inputs, success comparisons or deadlines. Require
actual execution of this diagnostic revision before choosing a behaviour fix.

[Diagnostic matrix 37888192740](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37888192740)
at source `5b7f4f15940aff7d495e08d19d4e26412f0dcc95` fails the ordinary experiment
at `after-E-detach`, request 6, F distance 5555/session 3. F's queue is inactive
and empty with unchanged session 3 and zero drops; its model remains Streaming,
zero model timeouts, zero DATA budget and zero drive. This observes invalidation,
not a swapped payload. Model counters do not prove the guest's failure cause.
The silence control and continued-DATA revision above require their own actual
qualification. Original and diagnostic failures remain preserved privately.

## Controls and actual acceptance

```sh
python3 tools/test_lump_two_port.py
python3 tools/test_lump_data_feeder.py
python3 tools/test_lump_queue_observer.py
python3 tools/test_lump_active_requests.py
python3 tools/test_lump_request_transport.py
python3 tools/test_lump_requests.py
python3 tools/test_lump_mailbox.py
```

The first five are pure Python host controls. The last two compile the actual C
request/mailbox core against host syscall doubles; they remain separate from ARM
execution. Adversaries cover swapped replies, cross-port consumption, unaffected
queue invalidation, reused replacement identity, wrong engine markers and
corrupted pending payload/session. Three mutations of the actual Python
comparison must fail assertions; setup exceptions do not count. Five additional
feeder mutations exercise queue count, session, front payload, report cap and
quiet-drain bounds. Ordered-drain adversaries reject missing, duplicate and
reordered frames; model transmission without guest admission is refused. Equal initial
cross-port session numbers are accepted. Existing F-only controls remain.

`simulation/renode/lump-active.robot` runs the old F-only case, detaches its model
and advances five simulated seconds, then runs the silence control and E/F case
on the same guest.
The complete hosted baseline matrix must rebuild both protected profiles and
pass every applicable guest/air regression, compiler/linker, attribution,
resource and TI-exclusion gate at the exact candidate source and pinned Runtime
and Infrastructure. Review raw logs and peer identities before adoption; host
controls or a green partial job do not substitute for actual guest acceptance.
Preserve failed invocations and raw receipts privately. Newly authored components
use BSD-3-Clause; existing firmware/model attribution and licences remain.

This still leaves arbitrary A–F combinations, cross-reset identity, concurrent
program readers, atomic PWM ownership, installed GUI/arena adoption and physical
behaviour unqualified. No reference image is used or required.
