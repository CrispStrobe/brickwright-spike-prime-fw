<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Protected userspace UART refusal probe

This candidate extends the [UART session prerequisite](lump-session-qualification.md)
with a real userspace syscall probe. Actual ARM execution is pending; host
self-controls are not a guest result. The one-shot `port simulation-poll-probe`
command and its implementation are included only when the existing protected
TI-free simulation and LUMP options are enabled. Hardware builds omit the command,
implementation and boot invocation. Configuration selections and dependency pins
remain unchanged; there is no new daemon or host request interface.

The non-HCI simulation boot script invokes the command after normal services.
NSH aborts a startup script on command failure, so a diagnostic refusal must not
prevent program startup. The HCI profile compiles the command but does not invoke
it automatically: its fixtures can attach a motor on F before boot.
It opens port F read-only, requires the observed device to be disconnected,
and makes fixed ioctl calls. It never sets PWM, changes a mode, resets an engine,
writes feedback or reserves a motor. A failed probe publishes failure and returns;
it does not wait, retry a user command, or substitute a successful result.

## Checks and publication

The probe calls the actual `LEGOPORT_LUMP_POLL_DATA_SESSION` syscall with null,
read-only guest flash, kernel RAM, an overflowing range and a range with only
36 bytes remaining in user RAM. Expected errors are `EINVAL` for null and
`EFAULT` for the other addresses. It then requires `EAGAIN` and byte-preserved
sentinel output from both the new 48-byte and legacy 36-byte inactive polls.
Finally it closes the read-only descriptor. No invalid address is dereferenced
by the probe itself.

The guest owns the 32-byte `g_bw_lump_probe` publication. Eight 32-bit fields
contain magic `0x42574c50`, version 1, state, completed-check bits, failure step,
syscall result, errno and the read-only object's address. State is zero before
start, one while running, two on success and three on failure. Success requires
all nine check bits (`511`), no failure/result/errno, and the exact ELF-resolved
read-only object within user flash. A memory barrier precedes terminal state.
This is an immutable one-shot result for the boot fixture, not a general
concurrent command mailbox or authority to control a motor.

The Robot fixture loads the ordinary protected pair and explicit existing
filesystem fixture, then lets the real boot script and scheduler execute. It
resolves the publication and read-only symbols from our ELF, bounds their ranges,
reads terminal state before and after the fields, and validates the result.
It writes no guest memory, feedback, function return or execution state after
normal initial image/vector setup. It runs in 20 ms guest-time increments,
bounded by 110 guest seconds and 575 host seconds, inside a 600-second test.

## Reproducible checks

```sh
python3 tools/check_lump_guest_probe.py
LUMP_TEST_CFLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' \
  python3 tools/check_lump_guest_probe.py
python3 tools/test_lump_probe_contract.py
python3 tools/test_simulation_startup.py
```

The host controls compile the actual probe with neutral syscall doubles and
cover fourteen success/failure/output-corruption scenarios. Two compiled probe
mutations must fail assertions: ignoring changed output and ignoring invalid
pointer refusal. Separate validator controls reject corrupt/missing publications,
guest failures and incorrect ELF addresses. Read-only host API doubles also execute
the actual observer through boot progress, failed/invalid states, guest and host
timeouts, invalid ELF ranges and paused-execution requirements. They expose no
bus write method. Three observer mutations must fail assertions: skipping terminal
validation, removing the host timeout and removing the guest timeout. These are
host probe/validator controls,
not actual guest kernel mutations. Boot preprocessing verifies that the command
is invoked after services in non-HCI simulation, omitted from HCI startup and
absent from physical builds.

The canonical `Firmware build and simulation` workflow now includes
`simulation/renode/lump-probe.robot` for the `simulation` profile, alongside the
existing protected regressions. Both clean profiles and all mandatory compiler,
linker-member, resource and TI-exclusion gates remain required. The inventories
add the two BSD-3-Clause probe inputs and prospective selected object, refresh
the modified utility/boot inputs and notices, and reproduce both historical
generated ROMFS hashes before deriving the candidate hashes. The new object's
byte hash is explicitly unmeasured until actual compilation; existing image and
archive byte hashes remain historical. No measured build or guest pass follows
from the prospective inventory.

New probe, controls, fixture and documentation use BSD-3-Clause. Retained utility,
boot-script, kernel and dependency notices remain applicable. This is not a
whole-firmware independence or licence-clearance claim.

## First hosted failure and correction

Source `9f597a047f92d4bafc07f300e04d96c2aa5dba6b` compiled both protected
profiles and passed their input/link/resource/TI gates in
[the first matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37751297921).
Its non-HCI job failed the existing board-isolated userspace milestone before
the new probe test ran: invoking the probe before `hubprogram serve` allowed its
missing-device refusal to abort NSH startup. Later tests were not executed under
exit-on-failure. This is a startup regression, not a successful syscall result.

The corrected startup places diagnostics after normal services and omits automatic
probe execution from HCI fixtures. The startup control fails against the original
ordering and passes the correction. Both historical ROMFS baselines were reproduced
before updating the corrected generated-input hashes. A new clean affected-profile
matrix is required; host controls alone do not qualify the correction.

## Remaining boundary

Even a passing inactive probe establishes only those protected syscall refusals
and output checks. It does not demonstrate a successful active session poll,
shared-queue consumption under known DATA, invalid-call non-consumption, reset,
same-type resynchronization, partial boot failure, physical MPU traps or hardware
safety. The HCI profile still runs its unchanged air scenarios; the new dedicated
Robot probe is qualified only where explicitly executed and recorded.

Next add a bounded real-userspace request interface for live external UART
stimuli, and qualify active identity, invalidation and replacement without queue
or session writes. A controlled external UART burst is needed to prove exact
non-consumption; continuous identical samples cannot do so. Conditional kernel
PWM admission and the one-second/20 ms readiness wait remain separate open work.
