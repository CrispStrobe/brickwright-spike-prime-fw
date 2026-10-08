# Current state and agent task lanes

Status recorded on **2026-10-05**. This is an executable handover for follow-up
work, not a claim that every lane is implemented. Start with the public source
and evidence below; refresh repository heads and check for already merged work
before choosing a lane. Public documentation contains repository paths and
public evidence only. Machine access, private images, operational commands and
private receipts belong in the operator's private agent instructions.

## Sensor lane checkpoint — 2026-10-08

The [inactive protected-worker mailbox](live-session-mailbox.md) is merged and
qualified. The separate [active F DATA experiment](active-session-qualification.md)
records its exact candidate, completed ordinary guest checks and remaining
companion-profile gate. It uses actual externally emitted UART DATA and a
read-only own-kernel queue witness; it does not broaden the program sensor API.
That record also gives a bounded two-port isolation follow-up with source entry
points, adversaries and guest acceptance criteria. Refresh its status before
starting L02 so these completed steps are not repeated. The baseline inventory
below remains historical; do not silently substitute its older dependency pins.

## Established baseline

[Brickwright firmware PR #34](https://github.com/CrispStrobe/brickwright-spike-prime-fw/pull/34)
merged at `603f33f856f0219149c4ad807c38642f5967e0b3`. Its tree matches reviewed
head `df3f500c6ae75493a4b0186e353a05812ac0fe2d`; that final commit changes
only documentation relative to tested source
`db67e6d1b7582cd5e61fb2880dd81ffed6828e76`.
[The complete firmware matrix](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37267297180)
and [merged-main CI](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37269883271)
pass. Exact scope is in [simulation qualification](simulation-qualification.md).

- Protected NuttX kernel/userspace boot and local program execution are qualified
  within the declared simulated board fixtures. The two simulation profiles
  differ in explicit virtual-HCI startup; both exclude the TI service pack.
- Native and embedded MicroPython uploads, retained restart after completion,
  stop or fault, cancellation and meaningful OSError results have host coverage.
  Actual ARM retained native/Python restart passes without another upload.
- Classic degree jobs use measured UART encoder displacement for supported
  motor types 48/49, wrap-aware accumulation and ownership-aware cleanup. This
  new path is host-qualified; a motor-coupled guest test remains open. Separately
  qualified six-motor topology evidence exists and must be preserved.
- Six Bluetooth-air scenarios pass: LE reconnect, Scratch Link, Classic/raw
  fusion, stationary readiness, poses/base axes and calibration persistence.
  These use a virtual controller; modeled encryption status is not a physical
  cipher/RF qualification.
- Calibration uses validated fixed-slot LittleFS save/load. The guest peer
  preserves learned bias through SAVE/STOP/LOAD/reopen while readiness resets.
  Real pinned LittleFS passes 63 calibration and 426 program crash/restart cases
  with simulated NOR and documented host boundary substitutions. Cold guest
  reboot and physical supply interruption are separate gates.
- Both protected profiles measure 593,932 bytes of userspace flash and 88,144
  bytes of static RAM, with zero TI payload bytes. These are candidate-specific
  static measurements, not stack/heap high-water marks or universal budgets.
- Current source, configured-input, attribution and history gates pass. Credited
  permitted Pybricks-derived components remain. This is neither a complete
  clean-room firmware nor full source/API replacement.

## Which projects and firmware routes are involved?

| Route or repository | Role and boundary |
|---|---|
| [Brickwright NuttX firmware](https://github.com/CrispStrobe/brickwright-spike-prime-fw) | Our experimental firmware, derived from spike-nx; contains selected credited robotics components, embedded MicroPython and a selected Zephyr host. Primary owner of lanes below. |
| Original [spike-nx](https://github.com/owhinata/spike-nx) baseline | Source ancestor. Rebuilt original images reached documented reset/bringup milestones; that does not establish complete original feature/radio support. |
| Stock LEGO firmware | Independently supplied unchanged reference input, not a repository dependency or published artifact. Latest bounded rerun completed 1.11 seconds of guest time, with no recorded CPU faults and no modern IMU notifications. Complete boot and wire mapping remain unqualified. |
| [Pybricks firmware](https://github.com/pybricks/pybricks-micropython) | Separate robotics firmware project and possible explicitly bounded behavioural oracle. Retained source grants and notices are recorded; whole-firmware parity is not claimed. |
| [Renode Runtime fork](https://github.com/CrispStrobe/renode-spike-prime) | Runtime, staging, board adapters and guest qualification. Firmware's current air-input inventory consumes immutable Runtime candidate `756b684eee56ba698a931a14b3f4885cb8d8ada6`. Runtime main has since advanced; do not silently replace the consumed pin. |
| [Infrastructure fork](https://github.com/CrispStrobe/renode-infrastructure-spike-prime) | Licensed hardware models. Firmware qualification consumes `fe4ad383c7392527433783fcec455daa7ddc2bb7`; main merge `4d4fefee12af854c124a85960d445e012e870bea` records that adoption. |
| Separate upstream-MicroPython application route | Runtime [PR #50](https://github.com/CrispStrobe/renode-spike-prime/pull/50), main `72a1c8a82681efdc035af71b0397a0cff40cdb1c`, adds bounded model-facing hub APIs. Read [its support contract](https://github.com/CrispStrobe/renode-spike-prime/blob/main/docs/spike-micropython-support.md). This is separate from NuttX's embedded interpreter and stock LEGO compatibility. |

## Shared frontend and version boundaries

[Brickwright Lite state and integration lanes](https://github.com/CrispStrobe/brickwright-lite/blob/1127285873b03ff6540809c15e627b946412f0c9/docs/SPIKE-STATUS-AND-LANES.md)
record the actual Code-tab/installed Linux GUI qualification from
[PR #631](https://github.com/CrispStrobe/brickwright-lite/pull/631). Small ARM guest,
full NuttX embedded Python and separately supplied upstream MicroPython routes
all exercised the shared hub/arena. This closes the earlier absence of installed
GUI evidence for those tested routes, not every new firmware feature.

The subsequent Lite [PR #695](https://github.com/CrispStrobe/brickwright-lite/pull/695)
adoption merged at `0faacb84211a5d6df8b4d3ed8ed9127c14b76fc5`, with reviewed
head `2b36862fb39f34a990eb296c734e9e800ed884c8`. Retained native/Python restart,
Stop ownership and installed Code-tab/shared-arena qualification are recorded in
[the updated consumer handover](https://github.com/CrispStrobe/brickwright-lite/blob/main/docs/SPIKE-STATUS-AND-LANES.md).
This is a separate finite desktop qualification; it does not adopt the newer
Classic Bluetooth motor candidate or close release provenance. Keep the desktop
profile, firmware test candidate and source heads distinct. Runtime
[task lanes](https://github.com/CrispStrobe/renode-spike-prime/blob/0bb3f3e40ec8e84afe6c7a63a03374a5a0553969/docs/SPIKE-STATUS-AND-LANES.md)
and Infrastructure
[model lanes](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/5a519ce5d9b5122bcf2ecedcbfd6f49d2735bbeb/docs/SPIKE-STATUS-AND-LANES.md)
own their implementation boundaries. Keep these versions distinct.

## How to execute a lane

For every lane, first read [capabilities](capabilities.md),
[qualification](simulation-qualification.md), [provenance](provenance.md),
[THIRD_PARTY.md](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/THIRD_PARTY.md)
and the current implementation at the listed public paths. Use the repository's
existing build/test instructions and workflows; repository-relative commands
below run from the owning repository root.

Write the observable contract before changing behaviour. Preserve existing
rights-holder notices and unsupported errors. Use a failing regression against
the old implementation when fixing a defect. Synthetic inputs must be declared;
do not replace guest functions, fabricate healthy readings or patch reference
application bytes to satisfy an integration gate. Separate model, host, guest,
reference and physical results.

A lane is complete when its stated acceptance tests pass, relevant CI is green,
and public capability/qualification records name the tested source, dependency
pins, evidence and remaining limitations. Firmware source/configuration/model
changes require clean affected-profile builds, compiler/linker-input review,
resource and TI-exclusion gates, and affected guest/peer regressions. Model
changes additionally require the owning Runtime/model suites. Documentation-only
changes require strict documentation and source-policy CI. Preserve historical
image/member evidence as historical; do not relabel it as a fresh measurement.

## Scheduling and dependencies

| Lane | Can start now? | Dependencies or external input |
|---|---|---|
| L01 Measured motor guest qualification | Yes; highest priority | Existing firmware and six-motor fixtures |
| L02 Arbitrary-port sensors and hotplug | Yes, contract-first | Coordinate shared port identity/ownership with L01 |
| L03 Cold-restart Bluetooth bonds | Yes | Existing virtual HCI and persistent media |
| L04 Cold-reboot storage and recovery | Yes | Existing LittleFS fixtures and guest loader |
| L05 Bounded hub I/O and power inputs | Yes, one device slice at a time | Public device contracts; physical calibration remains external |
| L06 Stall detection and HOLD | Contract/model work now | L01; physical tuning/qualification before hardware claims |
| L07 Modern IMU compatibility | Decoder/experiment preparation now | Independent paired reference observations for mapping |
| L08 Unchanged-reference model bringup | Public model regressions now | Lawful private reference input for boot diagnosis |
| L09 Python routes and desktop integration | Public contract/test work now | Separate application inputs for actual upstream-MicroPython runs |
| L10 Concurrency, resources and soak | Yes | Add scenarios as L01–L05 close; retain current hard budgets |
| L11 Reviewed dependency adoption | Yes, bounded review | Exact source/configuration closure and full affected qualification |
| L12 Optional robotics source replacement | Inventory/contracts now | Explicit separate implementation scope; not prerequisite to licensed simulation |
| L13 Physical qualification and release | Documentation/fixture plan now | Identified hardware, instruments and operator supervision |

Suggested first parallel allocation: L01, L02, and one of L03/L04; a fourth
worker may review L08 or L11 without touching firmware's shared inputs. Give
workers separate branches/worktrees and file ownership. Integration owns
cross-lane ABI changes, pins, inventory updates and the final matrix. L02 and
L06 must agree with L01 before changing the motor/attachment interfaces.

## L01 — Couple Classic degree jobs to guest motors

The [Classic motor peer contract](classic-motor-qualification.md) defines the
separate external readiness, motion and error comparisons being developed for
this lane. The complete candidate peer now passes signed/concurrent A/B motion,
Stop/replacement, loaded timeout and boundary errors; see the exact tested
source and remaining qualification gates in that contract. Attachment/disconnect
and the other excluded guest interleavings remain open; L01 is not complete.
A separate [encoder attachment-snapshot candidate](encoder-attachment-qualification.md)
adds host coverage for a connection edge during frame collection; it still
needs electrical attachment/ownership qualification and does not solve atomic
admission. Both clean protected profiles and the Classic motor peer now pass
on its recorded source; the exact attachment-change interleaving remains
host-only. Its full air suite and mandatory hosted fingerprint check remain open.

**Start:** firmware `apps/btsensor/btsensor_classic.c`,
`apps/btsensor/btsensor_modern_backend.c`, their `test/` fixtures,
`simulation/bluetooth-air/test_spike_air.py`, and Runtime
[the six-motor fixture](https://github.com/CrispStrobe/renode-spike-prime/blob/main/tests/firmware/nuttx-six-motor-fixture.py).
Read [hubprogram](../hubprogram.md) and [Classic protocol](classic-protocol.md).

Add a separate bounded Classic-air motor scenario. Drive real ARM command
handling, PWM/UART device models and encoder feedback; observe displacement
and end actions rather than writing completion state. Cover positive/negative
moves, multiple active ports, cancellation/disconnect, no progress, attachment
loss, stale ownership and a replacement job. Rerun the existing six-motor
profile on current firmware before describing new simultaneous A–F coverage.
Keep motor type/mode limits explicit. Counter wrap and timer-rearm failure may
remain synthetic targeted fixtures if the guest experiment cannot naturally
reach them; label that split.

**Acceptance:** measured target completion stops the owned job once; timeout or
loss fails explicitly; an old job cannot stop a new owner. Host checks
`tools/check_btsensor_classic.sh` and
`tools/check_btsensor_modern_backend.sh`, the new peer and the current-source
six-motor regression pass. Record supported topology, actual encoder evidence,
latency bounds and exclusions. This lane does not implement HOLD or a measured
stall detector.

## L02 — Generalize sensor addressing and attachment generations

**Start:** `apps/hubprogram/device.c`, `apps/hubprogram/motor.c`,
`apps/hubprogram/micropython/brickwright_module.c`,
`apps/btsensor/sensor_sampler.c`, `apps/btsensor/btsensor_nuttx_snapshot.c`,
and Runtime [LPF2 catalog](https://github.com/CrispStrobe/renode-spike-prime/blob/main/docs/platforms/lpf2-device-catalog.md).

Document which identities/modes each API supports. Replace fixed C/D/E
assumptions with validated A–F selection where the underlying driver supports
it. Carry attachment generation, identity/mode and freshness to consumers;
reject old readings and invalidate readers/jobs on replacement. Define wrong
reader recovery and unsupported errors before adding new identities. Use
alternate topologies, unplug/replug, wrong-type requests and damaged frames.
Coordinate shared ABI changes with L01; do not apply PWM to a sensor.

**Acceptance:** matching fresh data works on every advertised port; missing,
wrong-mode/type and replaced attachments fail without stale output or motor
actuation. Existing program and transport tests, new topology/hotplug host
regressions and representative real guest sensor workflows pass. Catalogue
entries alone never count as implemented API support.

## L03 — Prove cold-restart bond reuse

**Start:** `apps/btsensor/btsensor_lifecycle.c`, the selected Zephyr settings
integration under `bluetooth/`, `simulation/bluetooth-air/test_spike_air.py`,
and [air qualification](simulated-bluetooth-air.md).

Trace where supported Classic/LE keys are stored. Add a scenario that pairs,
terminates the owned emulator process, then starts a new process with exactly
the persisted medium and reconnects. Restore the peer's matching key state
explicitly; distinguish hub-key persistence from client caching. Test deleted,
wrong and corrupt keys, interrupted storage and pairing recovery. Add concurrent
Classic/LE traffic and explicit SMP/security rejection cases after cold-key reuse
is established. Document
which virtual security behaviours are modeled.

**Acceptance:** new-process reuse is demonstrated by the supported protocol/key
exchange, not just reconnect success in one session. Invalid keys fail or repair
under a stated policy without bypassing authentication. Existing six peers and
new lifecycle/storage tests pass. Physical encryption and RF remain open.

## L04 — Qualify storage across cold guest reboot

**Start:** `apps/hubprogram/storage.c`, `apps/imu/imu_calibration.c`,
`tools/test_littlefs_power_loss.py`, `tools/test_imu_littlefs.py`,
`simulation/renode/program-workflow.robot`, and
[filesystem fixture contract](synthetic-littlefs-fixture.md).

Add fresh-emulator save/exit/load/restart tests for native/Python programs and
calibration. Carry exact flash bytes between processes; keep persistent media
separate from RAM/service state. Inject failures at observed guest NOR operation
boundaries, remount, and test first save/replacement and nonblank damaged media.
Do not autoformat damaged media to manufacture success. Specify whether a
versioned/checksummed calibration record is needed; migrate the retained native
layout only with an explicit compatibility and corrupt-record policy.

**Acceptance:** cold reboot yields old/new complete records or an explicit
recoverable failure, without silently deleting existing media. Failed loads
preserve live state. Actual NuttX VFS evidence is distinguished from the existing
489 host LittleFS cases. Cold guest interruptions still do not prove physical
brownout durability.

## L05 — Complete bounded display, sound, button and power operations

**Start:** `apps/btsensor/btsensor_nuttx_peripheral.c`,
`apps/btsensor/btsensor_sound.c`, `apps/battery/battery_main.c`,
`apps/sound/sound_main.c`, [hub contract](hub-contract.md), and public
Infrastructure device models. The separate MicroPython route has its own
[hub I/O contract](https://github.com/CrispStrobe/renode-spike-prime/blob/main/docs/spike-micropython-support.md).

Choose one operation slice per change. Map request, guest driver, model state
and observable output; write missing/unsupported/stale errors first. Verify
matrix ordering, buttons and output ownership; distinguish display register
latching from brightness timing, and PCM observation from scheduled playback.
For battery/temperature, add documented raw ADC stimuli and actual conversion
through the guest driver. Do not infer a healthy battery from unknown data.
Keep button-ladder and power-management effects consistent across consumers.

**Acceptance:** each advertised operation has bounds, rejection tests and an
actual guest observation. Power events exercise stop/shutdown/failure policy;
physical calibration, audio output and electrical claims remain separate.

## L06 — Define and implement measured stall/HOLD capabilities

**Start:** L01 evidence, `apps/hubprogram/motor.c`,
`apps/btsensor/btsensor_modern_backend.c`, and retained motor/drivebase contracts.

First specify feedback freshness, target/tolerance, current or torque evidence,
load assumptions, timeout, ownership and cancellation. A no-progress timeout
must not be relabeled measured stall detection. Decide which supported device
capabilities can establish a stall. Build a bounded position-hold controller
with explicit disturbance, detach and ownership transitions; unsupported devices
must still reject the option. Add deterministic model loads and fault stimuli.

**Acceptance:** only the declared capability returns success. Synthetic load,
stale feedback, disturbance recovery and replacement-owner cases pass through
the actual guest. Record controller/resource bounds. Hardware tuning and motor
safety require L13; do not enable a hardware release from simulation results.

## L07 — Establish modern IMU mapping from independent observations

**Start:** [capture schema and experiment plan](imu-reference-captures.md),
`simulation/bluetooth-air/imu_reference.py`, `tools/test_imu_reference.py`,
`apps/btsensor/btsensor_modern_notify.c`, and [BLE inventory](ble-protocol.md).

Prepare capture validation and the experiment ledger now. Collect paired raw
notifications and independently known poses/motions or public API observations:
six faces, signed rotations, mixed-axis order, wraps/singularities, several
rates, yaw faces, resets and errors. Record source/version/time uncertainty.
Fit units/axes/Euler/reset rules on one set and validate held-out motions. Do
not derive the mapping by guessing from synthetic pose tests or inspected
private application implementation. Keep `wire_mapping_qualified=false` until
the evidence supports a separately reviewed conversion.

**Acceptance:** a traceable contract and held-out regression data establish each
advertised field. Rejections and quantization are covered. Without independent
reference observations, complete the tooling/experiment preparation and state
that conversion qualification is blocked; do not invent a passing mapping.

## L08 — Advance public hardware models and unchanged-reference boot

**Start:** [reference execution record](imu-reference-captures.md), Runtime
[MicroPython support](https://github.com/CrispStrobe/renode-spike-prime/blob/main/docs/spike-micropython-support.md),
and Infrastructure [DMA](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/main/src/Emulator/Peripherals/Peripherals/DMA/STM32DMA.cs),
[ADC](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/main/src/Emulator/Peripherals/Peripherals/Analog/STM32_ADC.cs)
and [SYSCFG](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/blob/main/src/Emulator/Peripherals/Peripherals/Miscellaneous/STM32_SYSCFG.cs).

Take one demonstrated public contract at a time. Independent sublanes are:
DMA manual-disable/interruption status and FIFO draining; ADC overrun/request
behaviour; SYSCFG memory remapping; remaining timer/clock/USB contracts. Full
DMA channel-mux/double-buffer/FIFO/error semantics and unequal widths need
separate specifications and fixtures. Diagnose bounded reference execution
using passive CPU/peripheral observations and expected public register semantics.
Check model regressions before rerunning the unchanged image. Keep host console
EOF/resource faults separate from guest faults. Do not patch reference bytes,
use function-return hooks or seed invented reference flash contents.

**Acceptance:** old model fails the concrete public-contract regression, new
model passes affected and full Runtime/model checks, then firmware adopts exact
reviewed pins through L11. Any reference milestone needs a bounded repeatable
observation; elapsed time or lack of a fault is not completed boot. This lane can
advance public model fixtures without reference access.

## L09 — Qualify Python routes and shared frontend integration

**Start:** NuttX `apps/hubprogram/micropython/`,
[program contract](../hubprogram.md), Runtime
[MicroPython support](https://github.com/CrispStrobe/renode-spike-prime/blob/main/docs/spike-micropython-support.md)
and its `tools/micropython/`, plus public
[Brickwright Lite](https://github.com/CrispStrobe/brickwright-lite) integration.

The baseline installed Code-tab routes are qualified as described above. Next,
adopt the newer firmware package and extend route-specific lifecycle/storage
coverage; do not repeat already completed GUI work as an unimplemented task.

Create a route-specific capability table: NuttX embedded interpreter versus
upstream MicroPython application with bounded SDK. Specify the next useful
robot API slice rather than promising complete LEGO/Pybricks modules. Test
upload/output bounds, stop/restart, timeout/interrupt and owner cleanup. For the
separate desktop route, qualify package/pin refresh, unavailable models, native
image admission and shared hub/arena inputs. Observation drives the world;
Python completion alone must not imply movement. Keep raw IMU samples separate
from orientation, PCM bytes from playback and model brightness from physical LEDs.
Portable installed-runtime discovery and non-Unix staging are independent
packaging subtasks; they must preserve closed input validation.

**Acceptance:** representative programs execute in the selected actual guest,
produce device observations, and recover from faults without stale ownership.
Document exact route/version/module limits. No firmware image is committed or
made available to the editor realm. Cross-route parity is claimed only for the
explicit tested subset.

## L10 — Measure concurrency, exhaustion and long-run recovery

**Start:** `apps/hubprogram/service.c`, `apps/btsensor/btsensor_scheduler.c`,
`apps/btsensor/btsensor_tx.c`, selected work queues, and
[resource budgets](resource-budgets.md).

Compose concurrent program, motor, sensor, radio and storage scenarios. Exercise
full queues, allocator/task failures, disconnect/reconnect, timer reschedule,
stop during startup, delayed shutdown and repeated reopen. Record bounded
wall/guest time, queue depth, stack/heap high-water marks and cleanup counters.
Test short failure sequences before a reproducible bounded soak. Do not weaken
budgets or accept dropped work silently to make a run pass.

**Acceptance:** admitted work completes or fails explicitly, rejected work does
not mutate ownership, and recovery has no leaked tasks/descriptors/timers or
unbounded resource growth. Preserve the normal matrix and add measured bounds
only when evidence justifies them. Hardware watchdog/thermal validation is L13.

## L11 — Review upstream changes and adopt immutable dependencies

**Start:** [NuttX backports](nuttx-backports.md), `tools/apply_nuttx_backports.py`,
`tools/test_nuttx_backports.py`, `policy/`, and
`.github/workflows/baseline-build.yml`. For newer Runtime work, start with
[PR #50](https://github.com/CrispStrobe/renode-spike-prime/pull/50).

Compare the pinned NuttX/Apps baseline and selected units against relevant
upstream fixes. Triage concrete bugs, security fixes and maintenance needs;
prefer a minimal reviewed backport when a broad version jump would obscure
behaviour. Verify the source licence and notices for every selected addition.
A separate packaging sublane can replace full dependency gitlinks with an exact
configured source closure and generate SPDX/SBOM plus linked-component evidence.
Compare two clean builds from different checkout locations before claiming byte
reproducibility; explain path/tool differences rather than normalizing away
unreviewed inputs. Retain the selected compiler runtime exception, and review
component-specific obligations for permitted MPL/LGPL selections as well as
MIT/BSD/Apache components.

Newer Runtime main is not automatically the firmware's new dependency: qualify
its affected adapters/models and update exact pins and inventories together.
Review actual selected linker members after clean builds, not just file headers.

**Acceptance:** each adoption has rationale, exact original/modification hashes,
retained notices, regression evidence and clean affected-profile CI. New linked
objects cannot bypass the selected-member gate. TI-restricted hardware payloads
stay outside TI-free simulation. Optional configurations remain separately scoped.

## L12 — Optional complete robotics-source replacement

**Start:** `policy/pybricks-reuse.json`, [reuse comparison](reuse-comparison.md),
[provenance](provenance.md) and `THIRD_PARTY.md`.

Inventory every retained robotics implementation and consumer, then choose one
bounded component. Produce a functional contract and synthetic fixtures. If a
two-team clean-room process is selected, record exactly who saw implementations,
what the implementation worker received and which access boundaries were actually
enforced; a fresh worker alone is not proof of isolation. Keep integration and
licence/provenance review separate from the implementation worker. A behavioural
oracle must be explicitly scoped and must not become an unreviewed source copy.

**Acceptance:** contract tests and representative guest behaviour pass, every
consumer is migrated, and the selected old implementation is absent from the
current build/source closure. Retain historical attribution where applicable
and document evidence without training-data or blanket independence claims.
Licensed reuse already permits the scoped simulation work; do not block L01–L11
on this optional architecture project or call partial replacement total removal.

## L13 — Physical qualification and release decision

**Start:** [physical qualification plan](hardware-qualification.md),
[SAFETY.md](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/SAFETY.md)
and [TI boundary](ti-service-pack.md).

Prepare hardware revision/configuration identification, instrument/setup records,
independent stop/current limits and expected results now. An operator with the
necessary hardware must execute boot/recovery, controller/eHCILL, interoperability,
port identity, measured motor motion/faults, IMU calibration, supply interruption,
power/thermal and resource/soak experiments. Record failures and uncertainty,
including the separate controller-service-pack licence/distribution decision.

**Acceptance:** each physical gate has actual identified evidence and remaining
defects; a release review explicitly decides go/no-go. Absent hardware, deliver
the reproducible experiment plan and leave physical gates open. Current source
remains simulation-only and no flashable artifacts are published by these lanes.
