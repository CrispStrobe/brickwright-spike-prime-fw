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
Each admitted report must have the exact 36-byte frame, no drops, one queued
entry and its own nonzero session. The fixture makes twelve sequential requests
and emits nine external reports. It does not create concurrent program readers.

1. Queue F=1111 and E=2222. Read F, witness E's original pending payload/session,
   then read E. Queue F=3333 and E=4444 and reverse the read order.
2. Queue F=5555 and E=6666. Run E's five refused calls and its successful poll.
   Verify F remains pending. Empty-poll E with all 48 sentinel bytes unchanged
   and again verify F remains pending.
3. Admit E=7777, detach E and witness actual inactive/empty E queue within five
   simulated seconds. Preserve F=5555/session before and after an empty E poll,
   then read F. This checks that E teardown discards its admitted report.
4. Reattach E, admit E=8888 and require its identity to increase within E.
   Admit F=9999, read E and witness F unchanged, then read F. F's identity must
   remain its original live identity. Finish with unchanged empty polls on both.

Sessions need not differ numerically across ports. Only the replaced port's
identity must progress. Sensor bridge drive must remain zero when sampled;
this is an observation, not a physical safety guarantee. Existing one-second
request, 200-ms emission/admission and cooperative host deadline bounds remain.
RunFor cannot be interrupted by those cooperative checks. Robot retains its
600-second timeout; no new hard process or mailbox cancellation claim follows.

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

The follow-up adds a checkpoint label/request ordinal, expected distance/session and the observed queue plus
public model state, timeout/frame/budget/drive counters to that failure. A secondary
diagnostic-sampling exception preserves the original deadline message. It does
not change firmware, external inputs, success comparisons or deadlines. Require
actual execution of this diagnostic revision before choosing a behaviour fix.

## Controls and actual acceptance

```sh
python3 tools/test_lump_two_port.py
python3 tools/test_lump_queue_observer.py
python3 tools/test_lump_active_requests.py
python3 tools/test_lump_request_transport.py
python3 tools/test_lump_requests.py
python3 tools/test_lump_mailbox.py
```

The first four are pure Python host controls. The last two compile the actual C
request/mailbox core against host syscall doubles; they remain separate from ARM
execution. Adversaries cover swapped replies, cross-port consumption, unaffected
queue invalidation, reused replacement identity, wrong engine markers and
corrupted pending payload/session. Three mutations of the actual Python
comparison must fail assertions; setup exceptions do not count. Equal initial
cross-port session numbers are accepted. Existing F-only controls remain.

`simulation/renode/lump-active.robot` runs the old F-only case, detaches its model
and advances five simulated seconds, then runs the E/F case on the same guest.
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
