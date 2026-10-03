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
readiness. The HCI case retains explicitly documented display-function hooks;
it is not complete board modeling. Existing-filesystem tests do not replace
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
A final reachable-history audit examined 100 commits and 1,258 blobs with zero
findings. That does not establish every historical line's authorship or inspect
all server caches and other clones. Build paths affect image hashes; complete
byte reproducibility across paths is not claimed. No firmware artifacts were
published by these jobs.

## Open reliability question

[An earlier public matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37101144091)
passed its default job but failed in the HCI job at the observed flash-initializer
return value, before Bluetooth startup. The old log did not print the value.
Its cause remains unexplained. Preserved, freshly rebuilt and CI-path-layout
pairs subsequently passed locally; a synthetic CPU probe did not reproduce a
suspected pause/return-register discrepancy.

Diagnostic logging was added without bypassing the mount, scan or zero-return
criterion. The final public HCI job records R0=0 inside the return hook and after
pausing at the same return address. Passing reruns are evidence of those runs,
not a claim that the earlier failure was causally fixed. Bounded repetitions
using a fully rebuilt final runtime are the next investigation step.

Physical USB/electrical behavior, motor safety, brownout timing, radio/security
and long-duration qualification remain open. Host fault injection does not
exercise electrical power loss or the complete NuttX VFS stack. See
[the simulation-only safety policy](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/SAFETY.md).
