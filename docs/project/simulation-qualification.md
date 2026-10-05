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

## CRC runtime qualification — 2026-10-04

The CRC qualification pinned Runtime
`a13be9696e84bd3485cc0a56401d1984b107cc9c` and Infrastructure
`ecd4fae6320b7f483b11dc4918e7182958f8ad36`. The STM32F4 CRC model now
handles its absent optional input-reversal field as disabled. Original Antmicro
and Pieter Agten MIT notices remain, with the modification notice added.

[Clean candidate Runtime CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37178545076)
passed native and managed builds, 290 focused model cases (including 20 CRC
cases), actual guest/debugger paths and throughput gates. The original model
failed both F4 cases while passing the other 18 cases; the rebuilt model passed
all 20. The offline MicroPython support profile retains its original reviewed
source pin; CI fetches that exact commit before offline verification so shallow
checkouts can supply the required object without weakening byte checks.

Infrastructure [PR 27](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/27)
merged at `720c4b10ffa6697b1ba5109c713586df77c51f4c` with the same tree as
the candidate. Runtime [PR 38](https://github.com/CrispStrobe/renode-spike-prime/pull/38)
merged at `59a8d92572aac992b9e89e2296dcc432ed042b55`, preserving a concurrent
drive-motor API addition. Its different combined tree passed
[separate clean main CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37179029874).
The firmware matrix below used the exact qualified Runtime candidate above.

[The complete firmware matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37178571908)
passed both protected profiles on `19997bf4700d66b719b7aa48e3ac7ceab2aa1bd6`.
Both rebuilt the pinned Renode from source and passed their resource,
licence/notices, TI-exclusion and actual guest gates. The HCI profile passed
LE reconnect, Scratch Link, Classic, stationary calibration and pose peers.
Userspace flash was 590,564 bytes for `simulation` and 590,556 bytes for
`simulation-hci`, against a 654,336-byte limit. Both used 87,816 bytes of
static RAM against a 98,304-byte limit, with zero TI payload.

The evidence-record commit changes documentation only. The new
[offline IMU capture decoder and bounded reference diagnostics](imu-reference-captures.md)
do not qualify modern IMU scales, Euler conventions or yaw behavior. The
reference application remains unchanged and private; it is not a firmware
dependency or published artifact. Runtime flash-checkpoint persistence checks
are source-level tests; guest filesystem evidence comes from the separate
firmware matrix.

Physical USB/electrical behavior, motor safety, brownout timing, radio/security
and long-duration qualification remain open. Host fault injection does not
exercise electrical power loss or the complete NuttX VFS stack. See
[the simulation-only safety policy](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/SAFETY.md).

## SPI Fast Read runtime qualification — 2026-10-04

The SPI Fast Read qualification pinned Runtime
`8c19f76437d9f395cd5ee3cb205ac7032abc64d8`, with Infrastructure
`5d2d3a79ed1df755fc261194de0774960d2ae0d3`. The native general SPI flash
model's Fast Read command (`0x0B`) now uses the selected three- or four-byte
address mode. It retains one dummy byte; the dedicated four-byte command
(`0x0C`) remains independent of that mode. The original Antmicro MIT notice
is retained, with a scoped modification credit.

An actual old-model negative control failed the four-byte-mode case while
passing the other 13 flash cases. The rebuilt model passed all 14 cases.
[Clean Runtime CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37182865383)
passed native and managed source builds, 296 model cases, and actual guest,
debugger and throughput checks. The offline MicroPython support profile
advances its reviewed source pin because the consumed flash source changed.
Of its 19 source inputs, the other 18 are byte-identical; its strict byte
verification is unchanged. Of 16 staged package files, only `models.cs` changes.

Infrastructure [PR 28](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/28)
merged at `15d1ac022b483d8e92f71c12e2ade154b4b7b566` with the candidate's
tree. Runtime [PR 41](https://github.com/CrispStrobe/renode-spike-prime/pull/41)
merged at `35cb7b2352f8448b7c2603853409143c5e590aa1`, preserving a concurrent
MicroPython sensor-reader addition. That combined tree differs from the
qualified candidate and passed
[separate clean main CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37184076166),
including all 296 model cases and the source, guest, debugger and throughput
gates. The firmware matrix below used the exact candidate pin above.

[The complete two-profile firmware matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37183121789)
passed on `9debccb86461e5c273bb36505bce9b18baded2dd`. Both jobs rebuilt the
pinned runtime from source and passed protected firmware execution, resource
budgets, licence/notices and TI-exclusion gates. The HCI profile passed LE
reconnect, Scratch Link, Classic, stationary calibration and pose peers.
Userspace flash was 590,564 bytes for `simulation` and 590,556 bytes for
`simulation-hci`, against a 654,336-byte limit. Both used 87,816 bytes of static
RAM against a 98,304-byte limit, with zero TI payload. The evidence-record
update changes documentation only.

This correction does not change the firmware's separate flash shim and does
not establish which flash commands the private reference application uses.
Modern IMU emission, full reference boot and physical hardware behavior remain
unqualified. See [the reference diagnostic scope](imu-reference-captures.md).

## Redirected console EOF qualification — 2026-10-04

The preceding console adoption pinned Runtime
`f1920f6bd9eee63026cb5620e8bc1c0bf9f7522f` and Infrastructure
`f6c31a7f8f223eb00378f88d7e2276792a1c392c`. The host console input worker
now stops at EOF instead of repeatedly forwarding `-1`. Before a subscriber
attaches it waits without consuming piped input; each blocking read retains
the delegate captured before that read. Original Antmicro MIT notices remain,
with a scoped modification credit.

Six synchronous fixtures cover empty EOF, finite input including NUL,
unattached and late subscribers, subscriber changes between reads and captured
delegate dispatch. A bounded equivalent of the original loop fails all six;
the explicitly rebuilt corrected helper passes all six. That local diagnostic
retained historical cached other sources and dependencies; it is distinct from
the complete clean source builds below.

[Console candidate CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37184175318)
passed on `48952c2408c7ba5f12bc3dd1c2ab73cd4f90b47d`.
Infrastructure [PR 29](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/29)
merged at `9b538871abbaad1b39c9e5fbbb50d872190a6f52` with the candidate's
tree. Runtime [PR 43](https://github.com/CrispStrobe/renode-spike-prime/pull/43)
merged at the pinned `f1920f6` commit, preserving a concurrent motor-feedback
addition. Its combined tree passed
[separate clean main CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37184652942).
Both runs passed native and managed source builds, 296 model cases, all six
console cases and actual guest, debugger and throughput checks. Console code
is outside the offline profile's 19-source closure; its strict verification
and reviewed source reference remain unchanged.

Separate real CLI checks rebuilt the complete Infrastructure source at `f6c31a7`
with cached dependencies and a historical CLI. Immediate finite piped commands
and commands sent after startup both produced their execution markers and
quit normally. At immediate EOF, the input thread was absent from the five-
and nine-second samples, memory stayed near 519–522 MiB and output remained
bounded. The monitor stayed open until the deliberate twelve-second wall cap;
EOF ends the input worker, not the monitor. These synthetic checks created no
machine and loaded no firmware image; they do not measure the queue length.

[The complete firmware adoption matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37184824092)
passed on `548e759e6cdc24991ceb662619977c89b21c83d7`. Both protected
profiles rebuilt the exact pinned runtime and passed guest execution,
resource budgets, licence/notices and TI-exclusion gates. The HCI profile
passed LE reconnect, Scratch Link, Classic, stationary calibration and pose
peers. Both profiles used 590,556 bytes of userspace flash against a 654,336-byte
limit and 87,816 bytes of static RAM against a 98,304-byte limit, with zero TI
payload. The simulation flash total was eight bytes smaller than the preceding
SPI qualification; the cause of that difference was not established. The
evidence-record update changes documentation only.

Modern reference boot and IMU wire mappings remain unqualified. The console
correction removes the host EOF defect; it does not supply missing ADC inputs,
SYSCFG behavior or reference notifications.

## ADC completion and SYSCFG routing qualification — 2026-10-04

The preceding ADC/SYSCFG adoption pinned Runtime
`99d7045205a049adfef4d1b13a45b54f47e3dbf5` and Infrastructure
`3f968455440204393d209f3d7941bc1304086eeb`. The ADC model now publishes EOC
before a synchronous DMA read acknowledges ADC_DR; SYSCFG reset now publishes
the held level of reset-selected port A. Original Antmicro MIT notices remain
with scoped modification credits. Actual original/changed synthetic tests
returned 8 ADC failures versus 13 passes and 33 SYSCFG failures versus 66
passes respectively. Those local diagnostics use cached dependencies. Actual
native topology tests and staged tests on the intended stock Renode 1.16.1
also passed the routing, four retained device endpoints, 13 ADC cases and six
UART bridges. Synthetic direct-EXTI bypass and missing-speaker-endpoint
mutations were rejected.

[Clean candidate CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37187564825)
and [separate merged-main CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37187927592)
passed complete source/native builds, all 378 focused cases (350 STM32/AM1808,
six console and 22 EV3 analog/motor), real native routing, guest execution,
debugger and throughput gates. Runtime main
`e49ecac194d3088314fec8c18be34c5101637d2d` and Infrastructure main
`183d84d7f4b16f0cde3c79be77223028549aff8d` have trees identical to their
respective tested candidates.

[The complete firmware matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37187575812)
passed on `132fff90c14e5c9d6a8c676a723b58f56c694586`. Both protected
profiles rebuilt the exact pinned runtime and passed guest execution,
resource, licence/notices and TI-exclusion gates. The HCI profile passed LE
reconnect, Scratch Link, Classic, stationary calibration and pose peers. Both
profiles used 590,556 bytes of userspace flash against a 654,336-byte limit and
87,816 bytes of static RAM against a 98,304-byte limit, with zero TI payload.
The final evidence update changes documentation only.

The native F413 platform now routes GPIO banks through SYSCFG EXTICR, retaining
PA13 power hold, PA15 display latch, PB12 storage select and PC10 speaker enable.
The offline source profile includes an aliased SYSCFG model and keeps strict
byte verification of its now 20-file source closure. The retained NuttX board
already had SYSCFG routing and explicit synthetic ADC fixtures.

At this preceding pin, DDS=0 DMA terminal-transfer handling remained open; the
following qualification addresses that synchronous model mechanism. SYSCFG
memory remapping and missing native battery/temperature ADC samples remain
open gaps. Full reference boot and
modern IMU wire mappings remain unqualified. No application disassembly or
firmware-specific register values were used for these corrections.

## ADC limited-DMA terminal qualification — 2026-10-04

The adoption pins Runtime `bac884d7af777be0e5552552188135d4e352e500` and
Infrastructure `8be722f931a5d0b82a2b866478e25efc3232df2f`. DDS=0 now allows
initial requests, then suppresses requests after the DMA controller's programmed
buffer completes. DMA stream re-enable alone cannot rearm the ADC; ADC DMA must
transition 0→1. DDS=1 circular transfers continue at buffer boundaries.

Independent named completion notifications preserve the existing eight IRQ
outputs. Descriptor/NDTR/EN/TCIF state is committed before acknowledgement;
acknowledgement precedes synchronous IRQ consumers that may rearm. The common
F4 map connects ADC1's existing DMA2 stream0 request pair to that notification.
The ADC accepts completion only while its own request is being serviced, so
another producer reusing stream0 cannot suppress it. This is a synchronous
model mechanism, not a physical GPIO or a TCIE/NVIC interrupt.

Four original-API tests fail on the actual original model; two ownership tests
fail on the first unguarded candidate. The corrected explicit managed build
passes 48 cases (29 new, 13 previous ADC and six DMA), zero skips or build
warnings/errors. Native board and intended stock Renode 1.16.1 staged fixtures
pass actual DDS=0 transfer/suppression/rearm with TCIE=0, all 29 new cases,
existing model fixtures, GPIO endpoints and six UART bridges. These local
cached-dependency scopes are separate from the clean runtime qualification
below and the firmware matrix. Original Antmicro MIT notices remain with scoped
credits; new fixtures are BSD-3-Clause. The strictly verified source closure remains 20
files: ADC/DMA change, 18 other inputs unchanged; output manifest remains 16.

[Clean candidate CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37198239632)
passed complete source/native builds, all 407 focused cases (379 STM32/AM1808,
six console and 22 EV3), actual GPIO/ADC-DMA topology, guest execution, debugger
and throughput checks. Infrastructure merge
`3ee16a8e46b79f634abda8282575694189f2c3c1` and Runtime merge
`ab9ec1bf70e8397c0ce541998917b26c84c2b857` have trees identical to their tested
candidates. The redundant Runtime merged-main run was cancelled when a separate
six-motor feature advanced main; this adoption retains its immutable tested
candidate rather than incorporating that separate feature.

[The complete firmware matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37198299149)
passed on adoption candidate `9ed7d2f9ae0cf6e78120732c77bde2612c3dd766`.
Both protected profiles rebuilt the exact pinned runtime and passed guest,
resource, licence/notices and TI-exclusion gates. The HCI profile passed LE
reconnect, Scratch Link, Classic, stationary calibration and pose peers. Both
profiles used 590,564 bytes of userspace flash against a 654,336-byte limit and
87,816 bytes of static RAM against a 98,304-byte limit, with zero TI payload.
The final evidence and historical-gap corrections change documentation only.

DDS=0 with circular DMA is a model boundary interpretation. ST recommends
limited requests with noncircular DMA and unlimited requests with circular DMA
in its [pinned LL header](https://github.com/STMicroelectronics/stm32f4xx-hal-driver/blob/1f6451c3e07728b4c830744de380e56bf5bc0026/Inc/stm32f4xx_ll_adc.h#L2638).
ADC overrun, asynchronous DMA timing, full channel-mux/double-buffer/FIFO/error
behavior and pointer state after manual abort were outside this preceding
qualification; its acknowledgement recovery fixtures use a fixed-address
(nonincrementing) destination. SYSCFG memory remapping, native battery ADC
sources, reference boot and modern IMU wire compatibility remain open.


## DMA partial-abort restart qualification — 2026-10-04

The adoption pins Runtime `31a43ea2be41e7baebe96df2d434f0136dc8065f` and
Infrastructure `43741b47a7fbdb74ae8c9abd670a6491c61642e8`. It reloads working
DMA pointers from programmed PAR/M0AR and the last software-programmed NDTR on a real EN 0→1 transition.
EN 1→1 control/interrupt-mask writes preserve transfer progress. To resume a
partial transfer instead of restarting it, software adjusts the bases and
explicitly writes the residual count before enabling. The contract follows
[RM0430 §9.3.15 and §9.5.6–8](https://www.st.com/resource/en/reference_manual/rm0430-stm32f413423-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
and [ST AN4031's resume procedure](https://www.st.com/resource/en/application_note/dm00046011.pdf).
Bare-restart count reload is a document-based interpretation, not a physical
measurement.

Enable dispatch runs after all control fields in the write have committed.
If a synchronous bus callback aborts and rearms while the old copy is returning,
the new descriptor's first work is deferred under its own generation. Disable
or reset cancels stale scheduled work. A new memory-to-peripheral request
received in that callback is retained without requiring another edge. The
model yields execution with a one-microsecond delay; this does not claim
cycle-accurate hardware timing.

All 51 new synthetic cases on the exact original model produce 34 failures and
17 passes, zero skips. The actual original native board also fails the new-base
restart assertion. The corrected managed build passes 153 focused NUnit cases
with zero skips or build warnings/errors. Native board and stock Renode 1.16.1
staged-source/board checks pass all 51 new cases, the existing model fixtures,
DDS=0 terminal handling, GPIO endpoints and six UART bridges. Package assembly
and six assembler tests pass. These local diagnostics use cached dependencies;
clean source/native runtime and firmware qualification below are separate
completed scopes. The source closure remains 20 files: only STM32DMA changes, and
19 other inputs including the MIT licence remain identical. Antmicro notices
are preserved with scoped modification credits; new fixtures use BSD-3-Clause.

The restart fixture checks receive/transmit, matched memory/peripheral
byte/halfword/word widths, independent memory/peripheral increment settings, buffer guards, programmed
versus residual count, whole-control writes and reentrant/cancelled work. The
actual ADC/DMA board fixture checks a partial buffer followed by a newly
programmed buffer and observes successful-buffer acknowledgement pulses.

[Clean candidate CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37200974971)
passed complete source/native builds, all 458 focused cases (430 STM32/AM1808,
six console and 22 EV3), the actual board abort/restart helper, GPIO topology,
guest execution, debugger and throughput gates. Infrastructure merge
`fbcfc30d7729d3dad2f0fb9089c4467f742edc06` and Runtime merge
`58a31066cc8164b0aa439fa8de59d9a487242885` have trees identical to their tested
candidates. The firmware retains those immutable tested candidate pins.

[Separate merged-main CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37201456088)
also passed all 458 focused cases and the complete source/native, board, guest,
debugger and throughput gates at the exact Runtime merge above.

[The complete firmware matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37200996536)
passed on adoption candidate `12de580fe15f7ecc1911316f4ae241130596c590`.
Both protected profiles rebuilt the pinned runtime and passed guest execution,
resource, licence/notices and TI-exclusion gates. HCI passed LE reconnect,
Scratch Link, Classic, stationary calibration and pose peers. Userspace flash
was 590,564 bytes for simulation and 590,572 bytes for simulation-hci, against a
654,336-byte limit. Both used 87,816 bytes of static RAM against a 98,304-byte
limit, with zero TI payload. The final qualification-record update changes
documentation only.

Nested peripheral-to-memory request pulses ending before an old copy returns
were outside these preceding restart fixtures; the following candidate
addresses that separately. Software-interruption TCIF and FIFO draining
remain unmodeled. Hardware's interruption status is distinct from the model's successful-buffer terminal
acknowledgement. Asynchronous DMA timing, ADC overrun, full channel-mux,
double-buffer/FIFO/error behavior, SYSCFG memory remapping, native battery ADC
sources, reference boot and modern IMU wire compatibility remain outside this
qualification. No private reference application is loaded or inspected here.


## Nested DMA receive-request qualification — 2026-10-04

The firmware pins Runtime `756b684eee56ba698a931a14b3f4885cb8d8ada6` and
Infrastructure `fe4ad383c7392527433783fcec455daa7ddc2bb7`. It retains a
receive-request pulse received inside a synchronous
copy callback until that copy returns. It applies both within the current
transfer and after callback-driven rearm. A real manual-disable edge discards
an ended pulse queued by the old descriptor, while preserving a still-high
request level. Automatic terminal completion keeps
the existing transmit readiness behavior. Falling edges outside an active copy
still cancel readiness. Requests held while disabled remain available on enable.
Reset and generation checks cancel stale deferred work.

This is a one-bit pending-readiness model, not a counted request FIFO or physical
timing qualification. Seventeen authored source-read fixtures check rearm with
manual disable/reset, matched byte/halfword/word widths, no-rearm nested pulses,
old/new source read counts, data/guards, successful-buffer acknowledgements,
old-generation isolation and held/cancelled readiness at rest. On the exact
original model, the first 15 cases fail nine and pass six, with zero skips. An
intermediate low-edge-only candidate fails two of those isolation cases and
passes 13, demonstrating
why manual disable must discard an old ended pulse. The broader first guarded
suite found a live-high SPI readiness regression; explicit input-level tracking
distinguishes held readiness from ended pulses. The final level-aware managed
build passes 170 focused cases including all 17 new ones, with zero skips or
build warnings/errors. Native board helpers preserve DDS=0 terminal handling,
abort/restart, GPIO endpoints and routing. Stock Renode 1.16.1 staged sources
pass all 17 new cases plus the previous source fixtures, board helpers and six
UART bridges. These cached-dependency local checks are separate from the clean
CI qualification below. Package assembly and six assembler tests also pass.

The consumed source closure remains 20 files: only STM32DMA changes, and 19
other inputs including the MIT licence remain identical. Antmicro notices
remain intact with scoped modification credits; new fixtures use BSD-3-Clause.
No private reference application is loaded or inspected.

[Clean Runtime CI](https://github.com/CrispStrobe/renode-spike-prime/actions/runs/37207122815)
passes 477 tests: 447 STM32/AM1808, six redirected-console and 22 EV3 tests.
Native board helpers, guest, debugger and throughput gates also pass.
Infrastructure PR #33 merged at `4d4fefee12af854c124a85960d445e012e870bea`;
Runtime PR #49 merged at `c1e64d35d5dc4723c5ae2e4a1d9f57cb689083a9`.
Both merge trees exactly match their tested candidates. The firmware retains
those immutable candidate pins.

[The complete firmware matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37207150835)
passes both protected profiles on adoption candidate
`7a70229841c2c35cbb0c12f745393c079b6ddef6`, including all five HCI peers
(LE reconnect, Scratch Link, Classic, stationary IMU and pose IMU).
Measured userspace flash is 590,556 bytes for `simulation` and 590,564 bytes
for `simulation-hci`; both use 87,816 bytes of static RAM and contain zero
TI service-pack payload bytes. This qualifies simulated synthetic IMU inputs,
not the unchanged LEGO firmware's modern IMU wire protocol.

Software-interruption TCIF, FIFO draining/disable latency, unequal-width
conversion, full DMA channel-mux/double-buffer/FIFO/error behavior, asynchronous
timing, ADC overrun, SYSCFG memory remapping, native battery/temperature sample
sources, reference boot and modern IMU wire compatibility remain outside this
qualification.

## Capability completion candidate — 2026-10-05

This source candidate adds retained-program restart and meaningful Python
OSError results, measured Classic degree jobs, owned cancellation/error
cleanup, and mounted-volume calibration persistence with validated live
stationary thresholds. The [capability matrix](capabilities.md) maps the
implemented subset and remaining gaps; the [hardware plan](hardware-qualification.md)
keeps physical gates separate.

Host program/service/embedded-Python, Classic/backend, neutral compile,
IMU snapshot/source/persistence/daemon and eight raw-reference decoder tests
pass. The daemon tests include UBSan float-cast-overflow and a 141-frame live
threshold-load/rejection/recovery case. Negative controls reproduce terminal
restart rejection, collapsed timeout errno, previous-record truncation on a
failed calibration save and ignored Classic cancellation rearm failure.
The prior calibration implementation fails the previous-record preservation
assertion; the replacement passes write/sync/close/rename failure isolation,
short I/O, exact record length and finite/nondegenerate validation.

The calibration crash/restart harness runs the actual save/load code against
pinned real LittleFS with simulated NOR: first save passes 18 cuts, ordinary
replacement 24, and replacement after 64 previous saves 21, for 63 cases.
Source hashes match the existing reviewed LittleFS closure. Its single-writer
unique-file shim and host filesystem boundary do not qualify actual NuttX VFS,
concurrent writers or physical brownouts. The original settings layout is
retained without checksum/authentication.

Clean ARM builds, actual linker-member changes and guest/peer execution remain
pending for this source candidate. Historical image/archive byte hashes in the
compiler-input inventories remain explicitly historical; reviewed current
source hashes and original attribution are updated. Additional libc members
from unique temporary creation must be checked against the actual build.
The unchanged reference rerun and its limits are recorded in
[reference captures](imu-reference-captures.md); it captured no modern IMU
notifications and does not qualify the wire mapping.
