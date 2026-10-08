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
at exhaustion. These host controls do not execute the ioctl or a NuttX kthread.

Required before merge: exact-source CI and both protected clean ARM profiles,
compiler-input/link/resource/official TI-exclusion gates, and affected compiled
guest scenarios. Direct guest qualification of the new ioctl and reset/session
transition remains necessary before a consumer relies on this API. Preserve
original failures and state exactly which boundary was exercised.

New queue/control/documentation components use BSD-3-Clause. Retained driver
and ABI attribution and MIT selections remain in place. The compiler-input
inventories add the actual helper and refresh only changed source/notice hashes;
component pins, permitted grants, linker selections and resource/TI gates remain
unchanged. This is not a whole-firmware independence or licence-clearance claim.

## Next implementation boundary

Use a snapshot's session at an atomic conditional board start boundary, coordinated
with current attachment and PWM ownership. A separate identity read followed by
an unconditional PWM write cannot satisfy this requirement. Then add side-effect-free
backend reservation and the one-second unpowered firmware wait with 20 ms polling,
including original connection lifetime and terminal reply admission. No user-request
host retries, cached feedback or fixture settling delays are part of this candidate.
