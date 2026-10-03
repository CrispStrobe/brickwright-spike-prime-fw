# Simulation qualification — 2026-10-03

The [firmware integration](https://github.com/CrispStrobe/brickwright-spike-prime-fw/pull/15)
is merged at `37c6e47583336c661ce9b6a0e2984158586de00c`. Its tree is identical
to the qualified candidate `507b382f2fc063e4c7e75c63826f6a9dacca3e92`.
This is experimental simulation qualification, not physical-hardware approval.

## Selected changes and evidence

[Reviewed NuttX backports](nuttx-backports.md) retain the existing dependency
pins and original author/licence notices. They address USB wakeup, protected
syscall bounds, descriptor/task failure paths, SPI DMA chunk continuation,
tickless compare handling and NSH failures. Storage recovery checks every byte
of the filesystem partition before formatting erased media; nonblank or
unreadable media does not authorize formatting.

Default `simulation` starts local program service with Bluetooth autostart
disabled. `simulation-hci` explicitly starts Bluetooth with a modeled controller.
Both exclude the TI service pack. The shared platform routes GPIO through
SYSCFG/EXTI and supplies explicit synthetic button/battery ADC values through
actual timer-triggered circular DMA. Synthetic values are fixtures, not
measurements of a physical hub.

Bluetooth synchronization changes broadcast to heterogeneous condition waiters,
serialize short list operations, enable PSA pthread locking and require NuttX
recursive mutex support. Actual host implementations passed adversarial queue
and list tests, 320,000 concurrent PSA known-vector operations and 2,000 complete
host-harness repetitions. These results do not prove all races impossible.

The installer pins Runtime `e0166acb028b162e972458f31d76cdb7dcdc518d` and
Infrastructure `e6c16afcc9598010e2aebc4d24af2f3d5d6bd7bc`. The runtime builds
native translators and managed code from source, retaining its pinned support
library dependencies. Model corrections cover iterative SPI DMA, configured
ADC rank/reset behavior, UART/I2C transmit readiness, idle request cancellation
and explicit F7 I2C byte data access. Original Antmicro MIT notices remain.
[Final merged-runtime CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37101102275)
passed 225 model tests plus guest, debugger, persistence and throughput gates.

[The complete firmware matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37102784250)
passed both clean protected ARM builds and source/configuration/linker, licence,
TI-exclusion and resource checks. Actual guest tests passed ADC/EXTI behavior,
tickless rollover, protected userspace, the exhaustive erased-flash first boot,
existing-filesystem mounting and standard-controller HCI startup through daemon
readiness. That matrix used explicitly documented display-function hooks;
the later display qualification below removes them from this HCI gate.
Neither result establishes complete board modeling. Existing-filesystem tests do not replace
erased-media first boot. Actual LittleFS crash/restart qualification separately
passed [426 interrupted-write cases](upstream-storage-hardening.md).
[Source and documentation CI on the merge](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37103489088)
also passed.

## Attribution and limits

Both profile inventories contain 3,245 conservative source/header/linker inputs
and retain their selected grants and notices. Properly attributed permitted
Pybricks-derived sources remain. Licensed adaptations are not claimed to be
cleanroom rewrites. The [third-party record](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/THIRD_PARTY.md)
and [provenance record](provenance.md) control component scope.
The integration's reachable-history audit examined 100 commits and 1,258 blobs with zero
findings. That does not establish every historical line's authorship or inspect
all server caches and other clones. Build paths affect image hashes; complete
byte reproducibility across paths is not claimed. No firmware artifacts were
published by these jobs.

## Flash-return observation race

[An earlier public matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37101144091)
passed its default job but failed in the HCI job at the observed flash-initializer
return value, before Bluetooth startup. That log did not print the value.
Preserved, freshly rebuilt and CI-path-layout pairs subsequently passed locally;
a small synthetic CPU probe also failed to reproduce the observation mismatch.

[Enhanced public diagnostics](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37104037545)
then reproduced the failure with decisive evidence: the return hook captured
R0=0 at PC `0x080095b0`, but the subsequent register read saw R0=`0x6590` and
PC=`0x080127de`. Flash initialization succeeded in this run; the test read a
later CPU state. The original uninstrumented failure lacks the values needed
to independently identify its exact state.

The hook published its milestone before requesting pause. Renode's log tester
could wake Robot immediately, allowing register reads before the hook's pause
completed. The corrected hooks capture return state first, request pause before
publishing the milestone, and explicitly await emulation pause. The test
requires both captured and paused R0 to be zero and both PCs to equal the
expected return site. It changes no guest registers and bypasses no mounting,
scan or formatting path. Precise pause is requested where supported; the
ordering and stop wait are essential, rather than an assumption that precision
alone is sufficient.

The corrected helper passed ten consecutive fresh-machine HCI boots on a
fully rebuilt final runtime: every captured and paused R0 was zero, and both
PCs equalled `0x080095b0`. The build used the pinned source and support libraries
without assembly overlays or reused runtime binaries. The VPS .NET runtime was
8.0.28; public CI used 8.0.31, so identical operating/JIT environments are not
claimed.

A separate actual-guest negative check loaded the validated synthetic fixture,
then corrupted the first 256-byte page of each metadata superblock using public
SPI operations. The unchanged guest returned `0xfffffff2` (`-14`, EFAULT) at the
observed return site. The helper correctly rejected this nonzero return. The
checked 8 KiB region was byte-identical after guest execution to its corrupted
pre-boot state; this readback is not a claim to have compared every byte of the
32 MiB chip. No fixture receipt was forged and no guest register was changed.

[The corrected two-profile public matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37104773113)
passed on candidate `71e061b66f30adc1ee4be92917c843674bc19a17`, including the
exhaustive erased-flash boot and standard-controller HCI startup. The subsequent
record update changes documentation only. These bounded results do not establish
universal firmware reliability or physical-hardware approval.

A subsequent [display candidate matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37108128568)
passed its default job and actual SPI/PA15 tests, but reproduced the observation
failure in HCI: atomic R0 was zero at `0x080095b0`, while the later read saw
R0=`0xafc8` at `0x080127de`. The earlier passing matrix and local repetitions
did not establish that the first correction eliminated the race.

Review of Renode's `LogTester.WaitForEntry` identified a remaining restart
window. An explicit `Start Emulation` before the waiter arms its predicate
allows the hook to stop execution first. If the initial log flush misses a
still-delayed message, the waiter can see emulation stopped and start it again.
Its buffered-message fast path also returns without awaiting stop. This is a
source-supported explanation of the public mismatch; the log alone does not
prove that exact scheduling interleaving. A controlled actual Cortex-M fixture
subsequently reproduced the restart mechanism: the old startup order captured
R0=0 at the synthetic stop site, then advanced to R0=7 while waiting for a
delayed notification. The new helper retained zero at the same site. The
notification carries values captured from the CPU; its producer is joined
before teardown. These synthetic cases are a durable `brickwright-milestone-wait`
regression, not a claim to reproduce every detail of the original host schedule.

`Wait For Paused Milestone` now synchronously stops emulation before the wait,
lets the waiter arm before its internal start, and synchronously stops again
after the wait to cover buffered matches. Milestone hooks request pause before
publishing their logs. Flash observation additionally requires the stopped CPU
to be at the actual initializer entry before reading LR, and retains both
atomic and stopped return-value/PC assertions. No firmware guest register is
changed. The synthetic instruction fixture is separate from the firmware.

The exact final helper passed 15 fresh-machine flash checks on .NET 8.0.31:
every stopped initializer entry, atomic/stopped return R0 and return PC matched
the required values. A full unchanged HCI boot passed in 97.65 host seconds.
Six local regression cases passed: display, ADC, EXTI, tickless timer, isolated
protected userspace and default existing-filesystem milestones. A corrupted
metadata boot retained the actual `-14` return at the correct PC; the zero
assertion rejected it, and the checked 8 KiB region remained byte-identical.
These additional checks use the freshly source-built pinned runtime with an
isolated .NET 8.0.31 runtime; they do not claim identical host scheduling.

## Digital display gate

The TLC5955 SPI1 byte sink is replaced by a digital shift/latch model. PA15
feeds both display LAT and its existing SYSCFG input. The
[model scope and TI interface reference](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/simulation/renode/README.md)
distinguish stored grayscale/control values from physical light output and
GSCLK timing. Deterministic reset values and zero SPI responses are explicitly
limited fixtures; analog current and SOUT/status behavior remain unmodeled.

The new `brickwright-display-latch` gate uses actual SPI1 byte accesses and
PA15 edges. Synthetic vectors check rolling shift retention, latch edges,
serialized/chip word order, control fields, matching maximum-current writes,
replacement confirmation, rejection without state mutation, and reset. Both
public firmware profiles select this gate alongside ADC/EXTI checks.

The existing-filesystem HCI gate removes its three display function
substitutions. It runs the unchanged guest driver and reads the display only
after emulation has paused at daemon readiness. Assertions require two accepted
control latches, at least one grayscale latch, no invalid command, complete
97-byte transfers and the board's expected DC/BC/MC/function values. Legacy
stub diagnostics and the separate Bluetooth-air helper remain explicitly
isolated; this change does not qualify those as complete board models.

The actual SPI/PA15 regression passed on the freshly built pinned runtime.
A separate unchanged `simulation-hci` guest boot passed all retained flash,
IMU and HCI assertions through daemon readiness in 168.74 host seconds. The
paused display contained five complete transfers (485 bytes): two control
latches, three grayscale latches and zero invalid commands. All 48 stored DC
values and all three BC values were 127; confirmed MC values were zero and
function bits were `0x19`. Serialized words 4, 7 and 14 were 65,535; the other
words were zero. These are stored register observations, not measured light
output. A private additional read-only snapshot captured the values after the
tracked assertions; it changed neither model behavior nor the guest. The
exact candidate then passed a five-case regression bundle: display, ADC DMA,
EXTI routing, actual guest tickless timer and default existing-filesystem
board milestones. The compiled firmware inputs and IMU/NOR model sources
are unchanged.

[The final two-profile public matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37109488565)
passed on `f7c7c8f7154ccabd856479405b2152d22ec832a6`. Both jobs passed the
controlled milestone negative/positive cases and actual display/ADC/EXTI gates.
The default job also passed protected userspace, tickless rollover, the
exhaustive initially erased-flash boot and existing-filesystem mounting. The
HCI job passed through daemon readiness with the real display driver in 36.88
host seconds; captured and stopped flash R0 were zero at `0x080095b0`.
[Source CI for the same candidate](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37109490928)
also passed. The intermediate matrix was superseded when the durable regression
was added; it is not cited as completed qualification. The final evidence-record
update changes documentation only.

Physical USB/electrical behavior, motor safety, brownout timing, radio/security
and long-duration qualification remain open. Host fault injection does not
exercise electrical power loss or the complete NuttX VFS stack. See
[the simulation-only safety policy](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/SAFETY.md).
