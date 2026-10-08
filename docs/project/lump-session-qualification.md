<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# UART DATA session prerequisite

This candidate is the UART feedback identity prerequisite for
[T04](tx-followup-lanes.md#degree-readiness) and L02. It is not the bounded
motor-readiness wait or an atomic motor-start implementation. No desktop
package, Runtime pin or physical hardware behavior is changed.

## Observable contract

The existing `LEGOPORT_LUMP_POLL_DATA` ioctl number and 36-byte frame layout
remain unchanged. The additive `LEGOPORT_LUMP_POLL_DATA_SESSION` ioctl uses
number `0x000D` within the existing port ioctl family and returns a 48-byte
`lump_data_session_frame_s`: a 64-bit session at offset zero, the legacy frame
at offset eight, and a zero 32-bit reserved tail at offset 44. Both polls
consume the same sixteen-frame queue; they do not duplicate feedback.

A nonzero session identifies one successfully completed UART synchronization on
one port during this boot. Repeated synchronization of the same device advances
it, even when the DCM device type does not change. Reset and session termination
invalidate and discard queued DATA under the queue mutex before UART release,
error callbacks or backoff. Poll while inactive or empty returns `EAGAIN` and
leaves output unchanged. Successful polls copy payload and session under that
same mutex. A poll that finishes before invalidation can legitimately return the
old identity; its later caller must revalidate before acting. The identity is
not a connection token, motor owner, timestamp, cross-port identity or authority
to perform a subsequent PWM ioctl.

The process-lifetime per-port counter is initialized once at engine bring-up.
Session reset never resets it. Boot-thread-only registration refuses a repeated
bring-up attempt, including after partial failure, rather than reinitializing
live threads, mutexes and counters; recovery then requires reboot. The host queue
controls do not inject NuttX bring-up failures. At 64-bit exhaustion, synchronization fails with
`EOVERFLOW`, the queue stays inactive, and no old identity is reused. A full queue
still drops the oldest DATA frame within an active session. Drop diagnostics
survive session end until reset or the next synchronization. Existing callbacks
and info/status ABI do not gain identity fields in this slice.

The new ioctl checks the complete user output range before consuming a frame;
null output returns `EINVAL` and invalid memory returns `EFAULT`. An older kernel
has no session ioctl; consumers must handle its unsupported-ioctl error rather
than silently substitute a legacy frame for conditional admission.

## Controls and remaining qualification

```sh
python3 tools/check_lump_data_queue.py
python3 tools/check_lump_session_ioctl.py
python3 tools/check_lump_registration.py
LUMP_TEST_CFLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' \
  python3 tools/check_lump_data_queue.py
```

These controls compile the actual engine queue helper. They cover FIFO/drop-oldest,
invalid inputs, unchanged output on refusal, invalidation before replacement,
per-port isolation, repeated synchronization and exhaustion. A condition-variable
schedule orders session replacement between two polls; a concurrent producer and
consumer check that returned payload/session pairs stay bound. Five compiled
mutations must fail assertions, rather than compilation: reuse identities,
retain old frames, admit unsynchronized DATA, publish a wrong identity and wrap
at exhaustion. The queue controls do not execute a NuttX kthread.

A separate Linux host control compiles the complete actual character driver and
its unchanged protected pointer-range checker with neutral NuttX service headers.
Only unrelated service calls and the engine pop boundary are stubbed; the pop
boundary uses the actual queue helper. It maps an unoccupied test range with
`MAP_FIXED_NOREPLACE`, never replacing host mappings. Invalid, overflowing,
read-only and legacy-sized output ranges must return before consuming a frame.
It checks refusal output preservation, shared legacy/session consumption and
session replacement through the actual ioctl switch. Three additional compiled
mutations fail assertions: validate only the legacy size, consume before the
range check, and copy output after a refused poll. This is host driver/control
coverage, not ARM privilege/MPU or guest syscall qualification.

The registration control compiles the actual, unchanged driver registration
function with neutral engine fields and faulting host service doubles. Thirteen
fresh-process scenarios cover successful registration and failures at each of
the six thread-creation and six handoff-registration calls. After each outcome,
three retries must return `EALREADY` without changing engine bytes, session
sentinels or service-call counts. Two compiled mutations must fail assertions:
removing the retry guard (all thirteen scenarios), and setting the started flag
only after complete success (all twelve failure scenarios). The latter mutation
also retains the successful-registration positive control. This does not run a
NuttX thread, inject failure into an actual ARM boot, or test concurrent bring-up;
registration remains a boot-thread-only interface. It adds no firmware inputs.

## Compiled regression checkpoint

Firmware source: `c47639d104c780f73d5ad548dffc316416019c63`.
Control/documentation head: `31494669e413b705418ce13500488b76611564ec`;
that follow-up changes only tests, their CI invocation and this document, with
firmware compiler inputs unchanged.
[Control CI](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37738082741)
passed both enabled checks.
[The protected matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37737419637)
passed both clean ARM profiles, including compiler-input/notices, selected linker
members, resource and zero-TI-payload gates. Both profiles passed the official
40-chunk fingerprint control; the new frame-size assertions compiled on ARM.

The HCI profile emitted seven complete PASS reports for LE/reconnect/periodic,
Scratch Link, Classic/IMU, stationary readiness, poses, calibration and measured
motors. All seven reports identify the same four kernel/userspace files by hash.
The other profile passed protected boot, actual ARM program restarts, interrupted
program storage and the empty filesystem seed. Only profile-inapplicable steps
were skipped. Both profiles measured userspace flash 595720/654336 bytes and
static RAM 88848/98304 bytes; these are userspace measurements, not kernel RAM
measurements or physical-hardware qualification.

The air helper again logged background peer-reset diagnostics while the reports
and job passed. Original logs retain those diagnostics; complete helper teardown
ownership is not claimed, and no dependency pin was changed to hide them.

Production callers still use the legacy poll. These compiled guest passes
exercise the changed shared queue through existing callers, not a new guest
session-ioctl consumer or injected partial bring-up failure. Direct guest
qualification of the new ioctl, invalid output and reset/session transition is
still required before a consumer relies on it. No arbitrary back-to-back motor
admission, physical accuracy or full equivalence follows from this checkpoint.
Final documentation CI and exact-head merge review remain required; no unchanged
ARM matrix rerun is needed for documentation-only changes.

New queue/control/documentation components use BSD-3-Clause. Retained driver
and ABI attribution and MIT selections remain in place. The compiler-input
inventories add the actual helper and refresh only changed source/notice hashes;
component pins, permitted grants, linker selections and resource/TI gates remain
unchanged. This is not a whole-firmware independence or licence-clearance claim.

## Next implementation boundary

The [protected refusal probe candidate](lump-guest-probe.md) adds a one-shot
simulation userspace caller for fixed invalid-output and inactive-poll checks.
It does not yet supply an active-session/reset guest result or motor authority.

Use a snapshot's session at an atomic conditional board start boundary, coordinated
with current attachment and PWM ownership. A separate identity read followed by
an unconditional PWM write cannot satisfy this requirement. Then add side-effect-free
backend reservation and the one-second unpowered firmware wait with 20 ms polling,
including original connection lifetime and terminal reply admission. No user-request
host retries, cached feedback or fixture settling delays are part of this candidate.
