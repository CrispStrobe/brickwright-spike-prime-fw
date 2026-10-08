<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Protected userspace UART refusal probe

This candidate extends the [UART session prerequisite](lump-session-qualification.md)
with a real userspace syscall probe. The corrected ordinary simulation profile
has passed actual ARM execution, and both corrected matrix profiles passed. Host
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
generated ROMFS hashes before deriving the candidate hashes. The initial inventory
represented the new object byte hash as unmeasured. The qualification update below records its measured hash from both profiles; other
image/archive hashes remain historical. A prospective inventory alone did not
establish a build or guest pass.

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
before updating the corrected generated-input hashes. The correction required
a new clean affected-profile matrix; its result is recorded below. Host controls
alone did not qualify it.

## Corrected matrix qualification

Tested firmware source: `87280884d15178ff5e1e6eb88545fb2d41441e1d`.
The following `e25c6d49928375128ead29447786fc0b529382c9` head changes only
startup-test comments, with unchanged firmware compiler inputs.
[Corrected matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37755707865),
[ordinary simulation job](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37755707865/job/113239602306):
completed successfully. The dedicated refusal test passed in 21.33 host seconds;
its actual observer requires all nine guest checks and the ELF-resolved read-only
address. This is not a measured guest-time or physical-device timing result.

That job also passed the compiler-input/notices and selected-member checks,
protected resource and zero-TI-payload gates, protected boot regressions, actual
ARM retained-program restarts, interrupted program storage and empty filesystem
seed checks. Its only skipped scenarios belong to the separate HCI profile.
Both matrix profiles completed successfully. The
[HCI job](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37755707865/job/113239601931)
passed its applicable input/link/resource/TI gates, transport bridge and seven complete air reports:
LE/reconnect/periodic, Scratch Link, Classic/IMU, stationary readiness, poses,
calibration and measured motors. All seven reports identify the same four firmware
files by hash. HCI compiles the probe but does not execute its dedicated syscall
fixture. The raw HCI log retains a background `ConnectionResetError` diagnostic;
passing peer reports do not establish complete helper-teardown ownership.

The actual selected probe object measured 13312 bytes, SHA-256
`ab5cda6b09be02714418d5d67bf0c28ba30a9bd84c094a08948a49c4fa6e1dcd`.
Both profiles measured userspace flash 596508/654336 bytes and static RAM
88880/98304 bytes. These are userspace static measurements, not kernel RAM or
stack/heap high-water marks. Existing historical image/archive inventory hashes
remain historical and do not identify these newly built images.

The test consumes the existing immutable Runtime
`756b684eee56ba698a931a14b3f4885cb8d8ada6` and Infrastructure
`fe4ad383c7392527433783fcec455daa7ddc2bb7` pair. It does not adopt or qualify the
separate external-DATA-budget candidates in
[Infrastructure PR #36](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/36)
and [Runtime PR #54](https://github.com/CrispStrobe/renode-spike-prime/pull/54).
Those candidates need compiled model and affected firmware qualification before
an active-session experiment relies on them.

## Remaining boundary

The passing inactive probe establishes only those protected syscall refusals
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

The separately tracked [replacement Runtime/model pair qualification](lpf2-budget-pair-qualification.md)
advances only test-host pins to exercise the external DATA-budget prerequisite.
It requires fresh affected guest regressions and does not replace this earlier
pair's evidence or establish active-session behavior.

The next candidate adds [fixed userspace requests](live-session-requests.md) for
live experiments. Its host controls and new inactive guest-publication fixture are separate
from the previously qualified source; actual new guest execution is required.
