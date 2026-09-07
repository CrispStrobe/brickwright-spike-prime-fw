# Brickwright SPIKE Firmware Plan

This is a fresh, parentless public source snapshot derived from
`owhinata/spike-nx`; private and upstream history is not reachable from it.
Project-owned and vendored source must use MIT, Apache-2.0, BSD-3-Clause, or an
explicitly approved comparable permissive licence, with no GPL-family, AGPL,
noncommercial, or source-incompatible terms. The exact unmodified CC2564C
service pack is the sole separately licensed binary exception and remains
governed by its adjacent TI-device-only licence.

The matching simulator accepts and acknowledges the opaque TI command stream;
it does not execute TI controller firmware or validate RF/electrical behaviour.

## Status legend

- `[ ]` not started
- `[~]` in progress
- `[x]` complete and verified
- `[!]` blocked; the checkpoint records the reason

Every completed checkpoint is committed and pushed independently. A checkpoint
is complete only when its listed verification passes and this file contains the
result and commit reference (added by the following checkpoint when necessary).

## Non-negotiable constraints

- Project source: approved permissive licences only; no GPL/AGPL/NC code.
- No BTstack in the target build or public source release.
- The sole restricted exception is the byte-exact TI service pack beside its
  licence; it must never be modified or presented as project-licensed code.
- Never reverse engineer, disassemble, or decompile the TI payload.
- Hardware loading accepts only known, unmodified TI payloads after hash and
  structural verification. Host code must handle eHCILL instead of patching a
  service-pack byte.
- Preserve copyright, license, provenance, and upstream commit information for
  every reused file.
- The legacy and modern wire protocols are isolated from the Bluetooth stack
  behind a neutral hub API and byte-level conformance fixtures.
- Simulator and firmware consume the same protocol fixtures wherever practical.
- No hardware-dependent step is marked complete using simulation alone.
- No flashable artifact or physical-installation instruction is published
  before the real-hardware safety gate is explicitly completed.

## Checkpoints

### C0 — Historical private-baseline migration

- [x] C0.1 Create the standalone private GitHub repository, retain `spike-nx`
  history, add an `upstream` remote, and push this plan.
- [x] C0.2 Record exact submodule commits, build prerequisites, flash layout,
  and a baseline licence/provenance inventory.
- [x] C0.3 Replace the Pages deployment workflow with private-repository CI that
  performs source hygiene, licence policy, and documentation checks
  without publishing artifacts containing restricted material.
- [x] C0.4 Reproduce the upstream protected NuttX build in a clean container and
  record binary sizes and hashes. No binary is uploaded while quarantined
  Bluetooth material remains; Bluetooth may be disabled for this gate.

Exit criteria: private origin confirmed, clean clone is reproducible, initial
CI is green, and every retained dependency has a recorded licence disposition.

### C1 — Permissive source boundary (historical migration)

- [x] C1.1 Remove BTstack from the build and submodule graph.
- [x] C1.2 Remove the embedded `cc256x_init_script` payload from Git history
  going forward; add a guard that rejects known payloads and suspicious large
  byte arrays. Historical private commits remain private until a later public
  history-export decision.
- [x] C1.3 Add a MIT/Apache-licensed TI service-pack installer that fetches a
  pinned official package from TI or accepts a local copy, validates allowlisted
  payload and licence hashes, preserves command bytes exactly, and writes
  ignored local build material.
- [x] C1.4 Produce a USB-only firmware after both restricted components are
  absent from the target source graph.

Exit criteria: licence CI rejects BTstack and TI payloads; USB firmware builds
without either; the importer has fixture-based tests that contain no TI bytes.

### C2 — Protocol contracts and conformance corpus

- [x] C2.1 Inventory the exact legacy SPIKE Classic extension: discovery,
  pairing assumptions, SDP/SPP details, framing, commands, replies, errors, and
  reconnect behaviour.
- [x] C2.2 Inventory both modern SPIKE BLE extensions: advertisements, service
  and characteristic UUIDs, framing/COBS/checking, commands, notifications,
  errors, and reconnect behaviour.
- [x] C2.3 Define the neutral `HubState`/hub-operation contract for ports,
  motors, sensors, IMU, display, sound, buttons, battery, and storage.
- [x] C2.4 Add licence-clean byte-level fixtures and parsers with malformed,
  fragmented, coalesced, timeout, and reconnect cases.

Exit criteria: every extension operation is implemented, explicitly deferred,
or explicitly rejected in an inventory; codecs pass native and JavaScript
fixture tests.

### C3 — Brickwright virtual SPIKE

- [x] C3.1 Implement the additive virtual Web Bluetooth backend.
- [x] C3.1a Repair the authoritative Classic/BLE extension transports, then
  regenerate Brickwright's bundled wrappers from the exact source commit.
- [x] C3.2 Implement the modern virtual GATT peripheral and protocol adapter.
- [x] C3.3 Implement the legacy virtual Scratch Link/RFCOMM session.
- [x] C3.4 Connect both adapters to one `HubState` and dashboard.
- [x] C3.5 Add end-to-end browser tests for motor output, sensors, display,
  disconnect/reconnect, malformed frames, and coexistence with real Bluetooth.

Exit criteria: the supported legacy and BLE extensions run representative
projects with no hardware or network and pass the shared protocol fixtures.

### C4 — Apache-2.0 Bluetooth host on NuttX

- [x] C4.1 Pin and audit the minimal Zephyr Bluetooth host source set needed for
  HCI UART, GAP, L2CAP, SDP, RFCOMM/SPP, ATT, GATT, and SMP.
- [x] C4.2 Implement the NuttX compatibility layer: buffers, allocation,
  atomics, synchronization, work/timers, entropy, settings, logging, and UART.
- [x] C4.3 Bring up a virtual HCI controller test harness on the host.
- [x] C4.4 Bring up Classic SDP/RFCOMM against the harness and conformance
  fixtures.
- [~] C4.5 Bring up BLE advertising/GATT/SMP against the harness and fixtures.

Exit criteria: both transports pass automated host-side tests without BTstack,
TI code, or physical hardware.

### C5 — Stock CC2564C hardware integration

- [x] C5.1 Integrate the exact vendored TI service pack and exercise its
  byte-preserving command stream through the Renode HCI seam.
- [x] C5.2 Implement and test eHCILL host wake/sleep handling rather than
  modifying the TI script.
- [!] C5.3 Validate controller initialization, shutdown, recovery, baud changes,
  ACL flow control, persistent keys, and repeated power cycles.
- [!] C5.4 Validate Classic pairing, reconnect, RFCOMM streaming, and the legacy
  extension on Linux, macOS, and Windows where available.
- [!] C5.5 Validate BLE advertising, pairing/bonding, GATT traffic, and modern
  extensions on the same platforms.

Physical CC2564C initialization remains part of C5.3. Simulation proves host
control flow and byte preservation only; it does not prove TI controller, RF,
or electrical behaviour.

Exit criteria: both protocols work on a physical SPIKE Prime hub, soak tests
pass, and logs prove that the imported service pack is byte-identical to an
allowlisted TI release.

### C6 — Firmware feature completion

- [~] C6.1 Connect the neutral hub API to all six Powered Up ports and supported
  motors/sensors.
- [~] C6.2 Complete IMU, display, buttons/LED, sound, battery, storage, update,
  and safe-failure behaviour needed by the extension inventories.
- [~] C6.3 Add resource budgets and tests for flash, RAM, stacks, queues,
  throughput, latency, and motor safety.
- [!] C6.4 Run USB/Bluetooth fault injection and long-duration hardware tests.

C6.4 is hardware-blocked for the same reason as C5. The hardware-independent
fault cases remain part of C6.3 and run in private CI.

Exit criteria: the firmware is useful for normal Brickwright projects and has
no known critical safety, data-loss, or recovery defects.

### C7 — Public-release readiness

- [ ] C7.1 Complete SPDX headers, `LICENSE`, `NOTICE`, provenance SBOM,
  dependency review, secret scanning, and reproducible-build documentation.
- [x] C7.2 Publish a new clean-root repository
  repository so no TI payload or disallowed BTstack snapshot appears in public
  history.
- [~] C7.3 Maintain pinned, least-privilege, artifact-free source/build CI;
  flashable artifacts remain forbidden until hardware validation.
- [ ] C7.4 Obtain legal review of TI import/distribution boundaries and assess
  Bluetooth SIG qualification/trademark obligations.
- [ ] C7.5 Perform a documented hardware-release go/no-go review.

Publication rule: the existing private repository and its refs are permanent
private archives because they contain historical LEGO dumps, TI service-pack
bytes, and build products.  Public release is made from a new single-root
source snapshot only after the current-tree gates pass; no private object or
parent commit may be reachable from that repository.

Until C5.3-C5.5 and C6.4 are completed on physical hardware, every public
source snapshot and repository landing page must say **simulation only — do
not flash to real silicon**. CI and releases must not publish flashable
firmware artifacts while this safety gate is open.

Exit criteria: all automated policy checks pass, legal/qualification questions
are recorded and accepted, and the public history contains only publishable
material.

### C8 — Instruction-level firmware simulation

- [x] C8.1 Pin Renode and add one STM32F413/SPIKE Prime platform model with
  the real 320-KiB SRAM and 32-MiB external-flash map.
- [x] C8.2 Add hash-verified local image acquisition and target manifests
  for official LEGO v2, official LEGO v3, original spike-nx, this fork, and
  Pybricks. Opaque or mixed-license binaries remain ignored local inputs and
  are never CI artifacts.
- [x] C8.3 Execute every target from its real vector table and assert bounded
  instruction-level progress. Use symbols for the two spike-nx builds and
  address/RAM observations for opaque binaries.
- [ ] C8.4 Model or deterministically stub the synchronous board peripherals
  needed to reach protected userspace and the application daemons without
  altering the production images.
- [ ] C8.5 Add deterministic CC2564C HCI, LPF2 port, display, IMU, storage,
  sound, and battery models at their hardware seams. The model accepts the TI
  command stream but does not execute, derive, or claim to validate TI's
  controller firmware.
- [x] C8.6 Add public ephemeral CI for redistributable inputs and a local
  matrix for all five targets. Keep USB electrical behavior, RF behavior, and
  physical timing explicitly assigned to C5/C6.4 hardware gates.

Exit criteria: all five actual ARM images cross their target-specific boot
milestones in one shared model; our unchanged protected production image
reaches its userspace and transport daemon; remaining model limitations are
machine-readable and cannot be confused with physical-hardware evidence.

### Next simulation-only roadmap

1. [~] Reconcile all public safety, licence, TI, and provenance documentation.
2. [ ] Replace full NuttX gitlinks with a hash-pinned, permissively licensed
   configured source closure; generate SPDX/SBOM and linked-component evidence.
3. [ ] Make public CI reproducible, SHA-pinned, read-only, and artifact-free.
4. [ ] Complete deterministic synchronous board models needed by unchanged
   protected firmware through userspace and daemon readiness.
5. [ ] Add HCI, LPF2, display, IMU, storage, sound, and battery models at
   hardware seams without interpreting proprietary controller firmware.
6. [ ] Complete BLE GATT/SMP and simultaneous Classic/BLE conformance through
   the actual ARM firmware image.
7. [ ] Run the five-family local matrix and connect Renode state to the
   Brickwright firmware/device/peripheral widget.
8. [ ] Add simulation fault injection plus resource, stack, latency, recovery,
   and soak gates.
9. [!] Define sacrificial-hardware validation only after steps 1–8; flashing
   remains prohibited until separately authorized.

## Checkpoint log

| UTC date | Checkpoint | Result | Evidence |
|---|---|---|---|
| 2026-09-07 | C7.1/C7.2 (publication audit) | In progress | Complete-history and current-tree audits found tracked compressed official LEGO flash dumps, historical restricted TI payloads, historical build products, an unused Pybricks gitlink, obsolete BTstack-bound sources, and a source-policy `.bin.gz` gap. Visibility remained private. Removed all current tracked dumps, the unused gitlink/build path, and dead BTstack adapters; disabled optional BSD components; expanded artifact suffix rejection and its black-box test; and made workflows visibility-neutral. A new root history is mandatory before publication. |
| 2026-09-07 | C7.2 (clean public root) | Complete | Published `CrispStrobe/brickwright-spike-prime-fw` from a parentless cleaned source snapshot. Earlier publication staging was returned to private visibility so removed private-backup references are not public history. The public snapshot includes the exact unmodified TI CC2564C v1.5 BTS and its byte-exact TI licence as a separately licensed hardware component, plus hash enforcement, NOTICE/third-party inventory, and a simulation-only/no-flashing safety gate. |
| 2026-09-07 | Roadmap step 1 (public truth/safety) | Complete | Reconciled the plan and TI documentation with the fresh public history and vendored service pack; converted the old baseline page into a non-actionable archive record; removed actionable DFU write commands from public documentation; and extended CI to reject their return while the simulation-only gate is open. Public build/simulation run `34094297122` and source/documentation run `34094880078` passed. |
| 2026-09-04 | C0.1 | Complete | Baseline cloned from `owhinata/spike-nx` at `00524ea5464bddb46c852967e382f8f6b073abe6`; `CrispStrobe/brickwright-spike-firmware` verified `PRIVATE`; upstream remote retained. |
| 2026-09-04 | C0.2 | Complete | Added `docs/project/baseline.md` and `docs/project/provenance.md`; recorded exact pins, build/flash inputs, policy exceptions, and unresolved audit items. |
| 2026-09-04 | C0.3 | Complete | Replaced Pages deployment with read-only private CI; source-policy and strict documentation jobs passed in GitHub Actions run `33914899646`. |
| 2026-09-04 | C0.4 | Complete | Private no-artifact run `33915185711` built both protected images after repairing and hash-pinning the dead NuttX-tools archive; versions, sizes, and SHA-256 values recorded in `docs/project/baseline.md`. |
| 2026-09-04 | C1.1 | Complete | Removed the BTstack gitlink/build prerequisite, disabled the dependent app, and passed private no-artifact firmware run `33915641046`; the user image fell by 103,028 bytes. |
| 2026-09-04 | C1.2 | Complete | Deleted the TI payload/licence from the current tree, added fail-closed path/hash policy plus a rejection test, and passed no-artifact firmware run `33916130202`. Restricted objects remain only in private history pending C7.2. |
| 2026-09-04 | C1.3 | Complete | Added a byte-preserving, local-only importer for the allowlisted official CC2564C v1.5 combined file; five synthetic tests plus documentation/source-policy CI passed in run `33917555415`. |
| 2026-09-04 | C1.4 | Complete | Private run `33916130202` built the USB CDC/NSH protected firmware with BTstack and TI files absent from the current source graph; no artifact was uploaded. |
| 2026-09-04 | C2.1 | Complete | Added `docs/project/classic-protocol.md`: separated Scratch Link, RFCOMM/SPP, and hub-stream contracts; inventoried commands/state records/errors/reconnect; identified the outbound-base64 defect and explicitly scoped Python compatibility. |
| 2026-09-04 | C2.2 | Complete | Added `docs/project/ble-protocol.md`: both extensions share one FD02 GATT/message protocol; recorded framing, negotiation, notifications, tunnel semantics, errors/reconnect, and extension defects against the published protocol. |
| 2026-09-04 | C2.3 | Complete | Added the versioned `protocol/hub-contract.schema.json` plus lifecycle documentation: neutral state, finite operations, events, units, error codes, stale-port generations, and transport-independent motor failsafe. |
| 2026-09-04 | C2.4 | Complete | Added independent SPIKE COBS/XOR fixtures plus Apache-2.0 C and JavaScript codecs; native/JS tests cover round trips, malformed input, fragmentation, coalescing, priority interruption, bounds, timeout, and reconnect reset. |
| 2026-09-04 | C3.1 | Complete | Brickwright commit `48850d448402b337da77afa157a9c957031956fe` adds a pluggable in-memory Web Bluetooth/GATT backend, additive wrapping of real/native Bluetooth, and discovery/connect/write/notify/disconnect tests. Targeted tests and `verify:bluetooth` passed; the full 2,115-test run had one unrelated pre-existing failure. |
| 2026-09-04 | C3.1a | Complete | Authoritative sources were fixed in `CrispStrobe/extensions` branch `feat/spike-transport-hardening` at `ff5e7485345b54de9e913760f68a9e58d1538091`: Classic sends UTF-8 as base64, direct BLE reassembles streams and uses serialized response-less packet writes, and both BLE parsers enforce corrected record bounds/signs. Brickwright branch `feat/spike-firmware-simulator` regenerates the three exact bundled wrappers at `9f544c49a12afae11053df68bf084a48bf6be319`; wrapper/source equality and virtual-Bluetooth tests passed. Repository-wide extension validation still has 28 pre-existing metadata/image failures and the global format check has two unrelated files. |
| 2026-09-04 | C3.2 (partial) | In progress | Brickwright commit `2929dc450f03594539cd2d2d39ee8e56dfabee8d` registers an FD02 virtual peripheral, reassembles fragmented COBS/XOR RX frames, answers Info and notification requests, translates the JSON motor tunnel, retains the reported-working Python tunnel for a bounded translator, and stops motors on disconnect. Five focused virtual Bluetooth/GATT tests pass. Device-record production and shared dashboard state remain. |
| 2026-09-04 | C3.2 | Complete | Brickwright commit `b8e6acb7ba4d4eae94ad95b94e30b5758adaac2b` adds device-record production for battery, IMU, motors, color, distance, force, and 3x3 matrix; deterministic dashboard-facing setters; a non-evaluating allowlist translator for basic Python motor tunnels; and an exact Apache-2.0 copy of the shared firmware framing vectors. Fourteen focused tests pass. Shared dashboard ownership remains C3.4. |
| 2026-09-04 | C3.3 | Complete | Brickwright commit `f025c308f8c7a0bcd2792e7ea17c51c59736728b` adds an explicitly enabled virtual Scratch Link BT socket with JSON-RPC discovery/connect/send, base64 RFCOMM bytes, CR/CRLF record assembly, current-state responses, bounded Classic motor-REPL translation, and disconnect failsafe. It remains inert for real Scratch Link and non-SPIKE Classic extensions. Sixteen combined simulator tests pass. |
| 2026-09-04 | C3.4 (state) | In progress | Brickwright commit `b9fc102afe1980e6f4ee241c367289b5b2767521` gives BLE and Classic one neutral state owner, synchronizes port/motor/sensor projections, centralizes the disconnect failsafe, and exposes a controlled browser API for the forthcoming panel. Seventeen focused tests pass. The visual dashboard remains. |
| 2026-09-04 | C3.4 | Complete | Brickwright commit `8461cb9e815c89c438365a23d977d9b47059f619` adds Settings → Virtual SPIKE Prime with explicit Classic enablement and battery, six-port, sensor, motor, matrix, and IMU controls over the shared state. Eighteen simulator tests pass. |
| 2026-09-04 | C3.5 (BLE) | In progress | Brickwright commit `97efbadec5e7703acc627abd617f7f939ed63f09` executes the actual bundled direct-BLE extension through connection, Info negotiation, streaming, motor output, dashboard sensor input, disconnect failsafe, and reconnect. Malformed-frame recovery was fixed and verified. Twenty combined tests pass; actual Classic-extension, display, and coexistence coverage remain. |
| 2026-09-04 | C3.5 | Complete | Brickwright commit `248b1db761bd25581a6504fd0441c9effbddece6` runs both actual bundled extensions through their virtual transports, covers motor/sensor/display state, malformed recovery, disconnect/reconnect, and profile-gated coexistence. The rendered brick selector distinguishes LEGO legacy v2 (Classic), official v3 (BLE), and Brickwright firmware (declared dual compatibility), with attached devices rendered on ports A-F. Twenty-two focused tests pass. |
| 2026-09-04 | C4.1 | Complete | Pinned Zephyr `v4.4.1` at peeled commit `1f6485eca25431b5ff27ce9a754218c9e559bbbb`; audited and machine-recorded the Apache-2.0 HCI/GAP/L2CAP/SDP/RFCOMM/ATT/GATT/SMP source boundary, exclusions, NuttX seams, PSA/Mbed TLS requirement, and independent TI/eHCILL boundary in `docs/project/zephyr-host-audit.md`. |
| 2026-09-04 | C4.2 (import) | In progress | Deterministically imported the 85-file reviewed Zephyr host subset (33 translation units, 51 headers, root licence) from the exact pin, preserved notices and paths, generated `files.sha256`, and made CI verify the manifest, Apache-2.0 declarations, file closure, and every byte hash. Kernel/NuttX compatibility implementations remain. |
| 2026-09-04 | C4.2 (core compatibility) | In progress | Added project-owned Apache-2.0 utility, GCC-atomic, atomic-pointer, and singly-linked-list compatibility primitives under the Zephyr include seam. A strict host test verifies values, bit transitions, CAS, pointer CAS, insertion, removal, FIFO order, and empty-list invariants. Configuration, buffers, synchronization, work/timers, settings, crypto, logging, and UART remain. |
| 2026-09-05 | C4.2 (data utilities) | In progress | Firmware commit `824a5ec` adds bounded endian get/put, byte-swap, unaligned-read, UUID text, and hexadecimal conversion compatibility. The exact pinned upstream `uuid.c` and `addr.c` compile unchanged under `-Werror`; executable tests cover FD02 short/full UUID conversion, canonical address parsing/rejection, LE address types, and deterministic static/NRPA bit construction. Private CI run `33942888800` passed. Buffers and OS services remain. |
| 2026-09-05 | C4.2 (simple buffers) | In progress | Expanded the audited import by one Apache-2.0 file to reuse Zephyr's pinned `lib/net_buf/buf_simple.c`. Added the minimum target configuration, compiler attributes, assertion/logging seams, wider endian operations, and kernel type declarations needed to compile it unchanged. Executable tests cover reserved headroom, add/pull, clone independence, reset, byte order, and tail removal. Pooled allocation, reference counting, waits, and synchronization remain. |
| 2026-09-05 | C4.2 (buffer pools) | In progress | Simple-buffer commit `55f45b5` passed private CI run `33943034008`. Firmware commit `56e7406` expands the exact Apache-2.0 import to 98 files, including pinned `lib/net_buf/buf.c`, its macro headers, and structurally required ISO declarations (ISO remains disabled). The unchanged upstream pool and Bluetooth `host/buf.c` units compile under `-Werror`. Executable tests cover fixed-pool exhaustion/reuse, reference counts, fragment teardown, timed LIFO wakeup, HCI event/ACL type prefixes, discardable/synchronous pools, and free callbacks. Private CI run `33943280094` passed. The current pthread/malloc host seam still requires validation against the pinned NuttX build. |
| 2026-09-05 | C4.2 (ARM buffer gate) | In progress | Split the atomic seam so Cortex-M4 builds use pinned NuttX's 32-bit atomic type without changing Zephyr semantics. Added a reproducible cross-compile gate for unchanged Zephyr simple-buffer, pool, and Bluetooth HCI-buffer units against NuttX `a67efb31cf4f236e456882589b91862f04594528`; local objects compile successfully and report text/data/BSS sizes. The gate is wired into private firmware CI. Linkage inside the complete NuttX image and target execution remain. |
| 2026-09-05 | C4.2 (ARM gate CI correction) | In progress | Private run `33944755739` built the complete protected firmware successfully, then exposed that the ARM gate was incorrectly launched on the runner instead of inside `nuttx-builder`; it exited before compilation because the cross compiler was not on the runner. The workflow now mounts the checkout and runs the gate inside the already-built pinned tool container. |
| 2026-09-05 | C4.2 (container ownership correction) | In progress | Rerun `33944986033` again built the protected firmware successfully and entered the containerized gate, where Git refused the runner-owned bind mount as a dubious repository. The gate did not require Git, so it now derives the repository root from its own absolute script location instead of weakening Git's safe-directory protection. |
| 2026-09-05 | C4.2 (semaphores/FIFOs) | In progress | Firmware commit `67ea82e` adds bounded counting semaphores and intrusive FIFO queues with no-wait, finite-timeout, and forever-wait behavior over the POSIX surface shared by host and NuttX. Host tests cover FIFO ordering, empty reads, delayed producer wakeups, saturation, reset, and timeout; private CI run `33945062426` passed. The Cortex-M4 gate compiles the same API against pinned NuttX. These primitives are currently thread-context only; any UART ISR handoff must use an explicit NuttX interrupt-safe adapter before C4.2 completes. |
| 2026-09-05 | C4.2 (ARM gate verified) | In progress | Workflow-fix commit `87d9a70` passed private no-artifact firmware run `33945179434`: the full protected NuttX images built, then unchanged Zephyr buffer units and the compatibility synchronization probe cross-compiled inside the pinned tool container. |
| 2026-09-05 | C4.2 (work queues) | In progress | Firmware commit `970c007` adds serial system/custom work queues, queue-thread identity, immediate and delayed submission, rescheduling generations, cancellation, synchronous cancellation, pending/busy state, and remaining-time reporting. Host tests exercise immediate execution, canceled timers, reschedule replacement, completion waits, and unchanged pinned Zephyr `long_wq.c`; private CI `33945490770` passed. The complete protected firmware and expanded Cortex-M4 gate passed in private run `33945491825`. Static resource budgeting remains before this slice is complete. |
| 2026-09-05 | C4.2 (entropy boundary) | In progress | Firmware commit `19f2412` selects the STM32F413 hardware RNG through pinned NuttX's Apache-2.0 `/dev/random` driver and adds a fail-closed `bt_rand()` boundary. It handles interrupted and short reads, clears partial output on failure, and exposes a weak backend so Brickwright simulation can inject deterministic entropy without emulating STM32 or TI services. Private CI `33945671993` passed; protected-image build and Cortex-M4 adapter gate `33945672738` also passed. On-device RNG health testing remains. |
| 2026-09-05 | C4.2 (logging boundary) | In progress | Firmware commits `179dbbf` and `4f6aba4` replace the no-op Zephyr log macros with bounded formatted and hex-dump output preserving level and module. NuttX defaults to syslog, host builds default to standard error, and weak filter/sink hooks let Brickwright capture simulator diagnostics while production suppresses debug output by default. Private CI `33946318820` passed; the later protected run `33946422893` includes the final logging implementation and passed. |
| 2026-09-05 | C4.2 (settings storage) | In progress | Firmware commit `c17c26b` adds the Zephyr settings registration/save/delete/name parser seam with strict logical-key validation, flush, and atomic file replacement under `/mnt/flash/brickwright-settings`. Weak store/remove operations let Brickwright provide an in-memory simulator backend without emulating flash. Host tests cover parsing, binary values, deletion, and traversal rejection; private CI `33946421736` and protected build/ARM gate `33946422893` passed. Loading/handler dispatch and on-device power-loss testing remain. |
| 2026-09-05 | C4.2 (settings loading) | In progress | Firmware commit `9230ad4` adds recursive LittleFS enumeration, registered subtree dispatch, priority-ordered commit callbacks, direct subtree loading, and exact path-component matching. Brickwright can replace enumeration and streaming reads with an in-memory implementation. Host load-routing/commit CI `33946859125` passed; protected run `33946990836` includes the implementation and passed. Unchanged Bluetooth settings translation-unit compilation and on-device power-loss testing remain. |
| 2026-09-05 | C4.2 (H4 framing) | In progress | Firmware commit `55b7a61` adds a bounded, incremental H4 stream parser for Event, ACL, and Classic SCO traffic above the existing `/dev/ttyBT` boundary. It handles fragmented and back-to-back packets and rejects unknown or oversized frames. The receive callback is directly usable by Brickwright without TI or STM32 emulation. Private CI `33946923925` passed; protected build/ARM gate `33946990836` also covers it. Zephyr `net_buf` delivery remains. |
| 2026-09-05 | C4.2 (H4 transport) | In progress | Firmware commit `3ba8cbe` adds open/close, poll-driven receive, short-write-safe transmit, and ioctl forwarding above an injectable POSIX byte-I/O seam. NuttX can point it at `/dev/ttyBT`; Brickwright can run the identical lifecycle against a virtual stream. Private CI `33946989606` and protected build/ARM gate `33946990836` passed. Zephyr `net_buf` delivery and daemon integration remain. |
| 2026-09-05 | C4.2 (H4 host delivery) | In progress | Firmware commit `1d47c24` adds Event/ACL delivery into unchanged Zephyr Bluetooth buffer pools with the H4 type prefix retained as required by `bt_hci_recv()`. The bridge checks minimum headers and pool tailroom, transfers ownership only on successful delivery, and rejects SCO because RFCOMM uses ACL and the selected host has no SCO buffer type. Private CI `33950209902` and protected build/ARM gate `33950211261` passed; daemon integration remains. |
| 2026-09-05 | C4.2 (work resource bound) | In progress | Firmware commit `f704a5d` replaces per-schedule heap allocation with an eight-slot static delayed-work request pool. Exhaustion now fails deterministically with `-ENOMEM`, canceled timer slots return after their deadlines, and recovery is tested. Timer threads remain one-per-live-delay but are strictly capped; consolidating them onto one timer thread is a later optimization rather than an unbounded-resource blocker. Protected run `33950290067` passed; its fast run was superseded by the following checkpoint. |
| 2026-09-05 | C4.2 (upstream settings compile) | In progress | Firmware commit `5143d92` adds the missing Apache-2.0-compatible `__weak`, hexadecimal-digit, and bounded decimal helpers, with direct success/error tests, and cross-compiles the pinned upstream Bluetooth `host/settings.c` unchanged against NuttX. Private CI `33950412623` and protected build/ARM gate `33950412657` passed. Full host linkage and power-loss testing remain. |
| 2026-09-05 | C4.3 (virtual HCI foundation) | In progress | Firmware commit `e59464b` adds a reusable, deterministic H4 virtual-controller endpoint with fragmented/coalesced command parsing, standard Command Complete responses for reset and BD_ADDR, and Unknown Command status for unsupported opcodes. Private CI `33950514575` and protected build/ARM gate `33950514681` passed. |
| 2026-09-05 | C4.3 (common/LE controller init) | In progress | Expanded the virtual controller with the pinned Zephyr host's mandatory common and baseline LE initialization commands: local version/features/supported commands, BR/EDR and LE buffer sizes, event masks, and LE host-support enablement. A byte-level initialization-sequence test checks response framing and advertised capabilities; native and Cortex-M4 gates pass locally. Classic initialization and executable full-host linkage remain. |
| 2026-09-05 | C4.3 (Classic controller init) | In progress | Added the Classic initialization commands selected by the pinned Zephyr host: SSP and inquiry modes, fixed-size local name, class of device, page timeout, BR/EDR buffer reporting, and default link policy read/write. Coalesced byte-level tests exercise the exact parameter lengths and response offsets. Runtime inquiry, connection, authentication, ACL, and RFCOMM events remain. |
| 2026-09-05 | C4.2/C4.3 (HCI core compile) | In progress | Firmware commit `b2ce7ac` closed the audited import around unchanged `hci_core.c` with pinned Apache-2.0 `testing.h` and `monitor.h`, plus narrow NuttX device, thread, stack-diagnostic, SoC, and time-unit shims. Added receive-workqueue selection, device identity configuration, FIFO inspection, range checking, and constant-time equality primitives. Private CI `33951192881` and protected build/ARM gate `33951193751` passed. Executable linkage remains. |
| 2026-09-05 | C4.2 (host-unit compile closure) | In progress | Expanded the audited pin to 110 files and the reproducible Cortex-M4 gate from isolated primitives to 28 unchanged Zephyr units covering common helpers, HCI core, advertising, scanning, identity, keys, connections, ATT/GATT, LE/Classic L2CAP, RFCOMM, SDP, and SSP. Added bounded memory slabs, mutex/condition-variable support, queue prepend, iterable sections, IRQ/spin locks, CRC-16, checked 16-bit addition, and explicit Kconfig defaults. PSA-backed crypto/ECC, unused SCO, and Zephyr's own H4 driver remain outside this gate; Brickwright's tested H4 transport replaces the latter. |
| 2026-09-05 | C4.2 (PSA provider pin) | In progress | Pinned Mbed TLS 3.6.2 tag commit `107ea89daaefb9867ea9121002fbbdf926780e98` and verified source archive SHA-256 `a3c959773bc5d5b22353bc605e96d92fae2eac486dcaf46990412b84a1a0fb5f`, selecting its Apache-2.0 option. Recorded the exact PSA operations required by Zephyr Bluetooth: RNG, AES-128 ECB/CMAC, P-256 key lifecycle, and ECDH. Minimal import/configuration and ARM linkage remain. |
| 2026-09-05 | C4.2 (host ABI correction) | In progress | Private fast CI `33952561289` exposed that connection TX user data sized for two 32-bit target pointers was too small for the 64-bit simulator ABI, although protected Cortex-M4 run `33952561496` passed. The shared configuration now reserves two native 64-bit pointers (16 bytes), retaining deterministic capacity on both ABIs. |
| 2026-09-05 | C4.2 (PSA compile gate) | In progress | Added a fail-closed Mbed TLS fetcher that verifies the pinned 3.6.2 archive SHA-256 and Apache-2.0 licence marker before extraction. A protected ARM gate compiles unchanged Zephyr host crypto, ECC, Bluetooth crypto, and CMAC units against its PSA headers. Added and tested the missing in-place byte-swap primitive. Mbed TLS library configuration/linkage and executable SMP tests remain. |
| 2026-09-05 | C4.2 (combined-link selection) | In progress | A combined relocatable-link probe exposed and resolved duplicate `bt_rand` ownership: production keeps Brickwright's NuttX hardware-RNG boundary while the unchanged PSA unit is symbol-renamed only for its unused RNG entry point. Enabled dynamic L2CAP required by RFCOMM, added SCO host compilation for Classic connection hooks, and supplied pointer/array helpers, XOR-128, mutex initialization, kernel-oops, division-rounding, and the L2CAP retransmission timeout. The expanded ARM unit gate passes locally; final Mbed TLS and linker-section resolution remain. |
| 2026-09-05 | C4.3 (native link closure) | In progress | Verified and pinned Mbed TLS framework commit `df3307f2b4fe512def60886024f7be8fd1523ccd` with archive SHA-256 `641fbb913f3ea6748cecbacb30af698d96de585f33d627f12b3ef9275b79726a`, then built `libmbedcrypto.a` with TLS, programs, and tests disabled. All selected Zephyr and compatibility objects now reach a native executable link with only the two empty SCO iterable-section boundaries unresolved. Added native ABI includes and timing constants discovered by this link. A safe empty-section representation and actual `bt_enable()` execution remain. |
| 2026-09-05 | C4.3 (executable host link) | In progress | Added explicit zero-callback sentinels for otherwise-empty SCO iterable sections and a reproducible native link gate. It verifies both pinned Mbed TLS archives, builds crypto-only `libmbedcrypto.a`, compiles every selected Zephyr host unit except the replaced Zephyr H4 driver, links all compatibility adapters, and executes the result. The local unoptimized proof is 1,101,505 bytes; actual `bt_enable()` traffic through the virtual controller remains before C4.3 completes. |
| 2026-09-05 | C4.3 (live virtual-host initialization) | In progress | Added one selectable Zephyr HCI device wrapper whose virtual backend uses the deterministic controller and whose physical backend uses the same `/dev/ttyBT` H4/net-buffer path with a bounded receive thread. The executable native gate now performs `bt_enable()`, the required settings-load transition, public identity creation, readiness verification, `bt_disable()`, and closed-state verification through real unchanged Zephyr host code. Repeated execution exposed and fixed event-pool starvation by applying receive-thread backpressure instead of dropping a Command Complete; the wrapper also cross-compiles against pinned NuttX. Runtime advertising, connections, ACL, and daemon ownership remain. |
| 2026-09-05 | C4.3 (live legacy advertising) | In progress | The virtual controller now validates and records legacy LE advertising parameters, advertising data, scan-response data, and enable state. The full unchanged Zephyr host executable starts and stops a non-connectable identity advertisement and verifies controller state. This exposed and fixed the compatibility queue's handling of work resubmission while its handler is running, with a focused regression test; back-to-back HCI completions no longer strand RX work. Connectable advertising, connection events, ACL, and GATT remain. |
| 2026-09-05 | C4.3 (virtual LE connection lifecycle) | In progress | Added deterministic virtual-peer LE Connection Complete and Disconnection Complete injection with controller handle/address state. The executable host gate now starts connectable identity advertising, receives a real Zephyr `bt_conn` callback, verifies advertising cessation, receives the disconnect callback and reason, and shuts the host down cleanly. ACL/L2CAP and FD02 GATT traffic remain for step 1. |
| 2026-09-05 | C4.3 (virtual FD02 GATT path) | Complete | Completed ordered step 1. The virtual controller now routes bidirectional ACL and returns Number Of Completed Packets credits. Enabled Zephyr connection TX, added the missing bounded fragment pool and conforming `k_work_flush()`, and added the real FD02 service with RX write/write-command plus TX notification/CCC characteristics. The executable unchanged host receives an ATT MTU exchange, accepts framed bytes at the FD02 RX value, enables notifications over ATT, and emits the expected FD02 TX notification over controller ACL. A 20-second harness deadline fails closed on deadlocks. |
| 2026-09-05 | C4.3 (virtual Classic connection) | In progress | Began ordered step 2. Added BR/EDR page/inquiry scan state, incoming Connection Request, Accept Connection Request command-status/completion, remote-feature completion, and disconnect handling. Corrected the compatibility thread-ID ABI to use Zephyr-style thread-object pointers, allowing synchronous HCI commands from the system work queue without deadlock. The host gate now completes both LE and Classic connection lifecycles; SDP/RFCOMM traffic remains. |
| 2026-09-05 | C4.4 (virtual Classic SDP/RFCOMM) | Complete | Completed ordered step 2. Added an Apache-2.0 Zephyr SPP server on RFCOMM channel 5 with a discoverable Serial Port SDP record and transport-neutral receive/send API. The executable host gate now drives real unchanged Zephyr BR/EDR L2CAP signaling, opens RFCOMM multiplexer and DLC sessions, delivers an SPP payload, opens an SDP channel, and discovers the registered Serial Port record. Virtual ACL completion delivery is generation-tracked to make host credit acknowledgements deterministic. |
| 2026-09-05 | C4.2 (daemon transport boundary) | In progress | Began ordered step 3. Added one Apache-2.0 daemon-facing transport API that tags incoming Classic and BLE bytes, tracks link availability, sends through RFCOMM SPP or FD02 notifications, and hides Zephyr connection ownership from the application. The executable host gate exercises this boundary over BLE and Classic; migration of the old command/telemetry daemon remains. |
| 2026-09-05 | C4.2 (daemon protocol boundary) | In progress | Added bounded transport-independent stream handling above the neutral link: fragmented/coalesced Classic CR/CRLF records, standalone interrupt bytes, and fragmented/priority-interleaved SPIKE COBS messages. Outbound logical records are framed only at this boundary. Native tests cover both protocols, malformed input, overflow recovery, and link dispatch; application lifecycle and peripheral operations remain. |
| 2026-09-05 | C4.2 (transport-neutral daemon) | Complete | Completed ordered step 3. Replaced the active `btsensor` BTstack lifecycle with a compact NuttX task owning the Apache Zephyr host, physical H4 transport, dual Classic/BLE visibility, distinct legacy and modern protocol paths, and orderly shutdown. The response/telemetry arbiter is thread-safe across Zephyr RX and producer workers, invalidates in-flight sends on disconnect, and invokes external callbacks unlocked. Ported IMU/sensor/bundle scheduling to one bounded poll/timer worker; it remains outside the first active image until the step-4 resource/link gate. Native, concurrent, and Cortex-M4 compile tests pass, and the active application Makefile contains no BTstack or TI payload input. Private CI `33974971784` and protected firmware gate `33974972892` passed. |
| 2026-09-05 | C4.2 (target host archive) | In progress | Began ordered step 4. Added a single deterministic Cortex-M4 archive producer for the selected Zephyr Classic/BLE host, Brickwright compatibility/services, PSA adapters, and hash-pinned Apache-2.0 Mbed TLS crypto. Added a NuttX application prerequisite and explicit protected-module link ordering, an STM32 RNG-backed Mbed TLS entropy hook, and enabled the neutral daemon in the SPIKE USB configuration. The archive compiles locally; complete protected-image linkage is pending the private remote gate. |
| 2026-09-05 | C4.2 (target link corrections) | In progress | The first complete protected link resolved the archive boundary and exposed target-only constraints. Matched NuttX's Cortex-M4 hard-float ABI, included SMP and hexadecimal helpers, supplied production SCO iterable-section sentinels, replaced compiler TLS with POSIX thread-specific identity, and reduced Mbed TLS to the exact PSA AES-ECB/CMAC, P-256 ECDH, and external hardware-RNG surface. The deterministic 130-object archive and all local neutral-daemon/host gates pass; the complete protected image is the next acceptance gate. |
| 2026-09-05 | C4.2 (protected footprint) | In progress | Protected run `33976833329` confirmed the ABI/SMP/hex corrections and narrowed the remaining failures to linker-retained SCO sections, unavailable NuttX pthread keys, and flash footprint. Added explicit user-linker iterable boundaries, replaced pthread keys with a bounded work-queue registry, gave PSA its own minimal feature manifest, and applied the target's size optimization consistently. Raw archive text fell from 355,836 to 197,017 bytes; another protected full-image gate remains. |
| 2026-09-05 | C4.2 (protected integration) | Complete | Completed ordered step 4 at commit `e0ffcb4`. Private protected run `33977401578` built and linked the active transport-neutral daemon, unchanged selected Zephyr Classic/BLE host, and minimal Apache-2.0 Mbed TLS PSA provider into the NuttX user image. All subsequent ARM boundary, PSA, and executable virtual-host gates passed. The no-artifact outputs were `nuttx.bin` 221,180 bytes (`b5f8d29b...44dfb`) and `nuttx_user.bin` 515,216 bytes (`3472333b...f07b`), leaving 9,072 bytes in the current 512-KiB user flash partition. Physical TI-controller initialization remains ordered step 5. |
| 2026-09-05 | C5.1/C5.2 (controller boundary) | In progress | Added a MIT transport-neutral BTS executor that streams byte-exact H4 commands from the ignored, allowlisted local container and validates only public BTS framing plus standard HCI completion/status responses; synthetic fixtures contain no TI bytes. Added Apache-2.0 eHCILL handling at the physical H4 byte-I/O seam with sleep/wake handshake, boundary-safe control parsing, synchronized RX/TX, and bounded queued TX. Added an independent lifecycle model covering power/reset, boot and controller baud transitions, deterministic unwind, bounded recovery, persistent state, and ACL credits. Synthetic gates pass; actual local TI import, lifecycle wiring, and physical-hub validation remain. |
| 2026-09-06 | C5.1/C5.2 (audited physical integration) | In progress | Audited and corrected the parallel controller work at `809bb95`: one lifecycle-owned service-pack load now spans reset, boot H4, byte-exact BTS execution, BTS serial transitions, eHCILL, Zephyr delivery, bounded fault recovery, and shutdown. Removed a duplicate pre-`bt_enable()` loader that reset away its own work, fixed an RX-callback/send lock inversion, and made latched wake timeouts recover. Private CI `34044791875` passed. Protected run `34044793416` passed with a nonfunctional synthetic placeholder reserving all 10,211 allowlisted payload bytes; `nuttx_user.bin` is 522,188/524,288 bytes. C5.2 is complete in synthetic coverage. C5.1 and C5.3-C5.5 still require the separately installed TI package and a physical hub; no TI bytes entered Git, CI, logs, or artifacts. |
| 2026-09-06 | C4.2/C4.3/C4.5 (host completion and SMP) | In progress | The protected target links the complete selected Zephyr host and compatibility layer. The deterministic controller exercises real LE and Classic connections, ACL, FD02 GATT, SDP/RFCOMM, legacy Just Works SMP through Mbed TLS, STK-validated encryption, Security Level 2, and nonempty bond serialization (`1059084`). C4.2 and C4.3 are complete. C4.5 remains in progress only for cold-restart bond reuse and Secure Connections/ECC; the supported extensions request no link security. |
| 2026-09-06 | C3.1a (authoritative fallback correction) | Complete | `CrispStrobe/extensions` branch `feat/spike-transport-hardening` commit `fe4f64f` rejects compact and JSON-RPC hub errors and creates Python fallbacks lazily. `CrispStrobe/brickwright-lite` branch `feat/spike-firmware-simulator` commit `dd9b744b7` adds a full-SHA source pin and deterministic overlay generator, regenerates the Classic wrapper, and passes 12 focused simulator tests plus vendor-freshness run `34048250657`. |
| 2026-09-06 | C6.1/C6.2 (finite peripheral slice) | In progress | Commits through `3eb7783` route motor and 3x3-matrix commands directly by physical port A-F, preserve cross-transport ownership, implement exact bounded Classic start/stop/timed motor plus 5x5 pixel/clear and beep operations, translate the proven modern motor/5x5/beep Python strings without evaluation, and publish battery plus non-destructive ultrasonic distance. Degree moves, stall detection, atomic images/text, coherent full sensor/IMU records, center LED/buttons, storage, and update operations remain explicit gaps. An IMU candidate was rejected during audit because zero-filled attitude and unproven raw units would misrepresent a complete record. |
| 2026-09-06 | C6.3 (budgets and safety) | In progress | Generation- and token-owned motor shutdown prevents stale disconnects and timed callbacks from stopping a newer transport owner. Bounded timer, queue, backpressure, malformed-input, sound-cleanup, and recovery tests landed through `b8bd2e8`. The protected gate caught a real 40-byte RAM overage after integration; commits `ed56825` and `8988ac6` removed an unused production I2C shell tool and reduced only the explicitly discardable HCI-event pool from three buffers to two. Final protected run `34049762481` passed at 461,428/523,264 bytes flash and 98,036/98,304 bytes static RAM with the exact 10,211-byte synthetic TI reservation; fast run `34049761469`, ARM boundaries, PSA units, and the complete host link also passed. Stack high-water, throughput/latency measurements, and physical timing/soak evidence remain. |
| 2026-09-06 | C1.3/C5.1 (separate TI package) | In progress | Replaced the project-invented licence-acceptance switch with the conventional Linux-firmware model. The MIT/Apache installer fetches TI's exact pinned Git revision or accepts an existing package, verifies both payload and accompanying TI licence hashes, and installs them together only under ignored `.local/ti/cc2564c/`. Source policy now derives forbidden hashes from the TI allowlist so neither file can enter Git. The real official v1.5 combined file installed locally as 10,211 bytes/162 BTS actions with the allowlisted hashes, and loader/lifecycle boundary tests pass. A local full build was attempted but this host denied access to its Docker daemon before compilation; protected CI proves the same target with an exact-size synthetic reservation. A real-payload build and physical-hub execution remain C5.1's missing evidence. |
| 2026-09-06 | C8.1/C8.2/C8.3 (opaque-image execution) | In progress | Pinned checksum-verified Renode 1.16.1, added the shared STM32F4 platform's missing upper 64-KiB SRAM and 32-MiB external-flash window, and added an authenticated hash-verifying importer for ignored private images. Actual official LEGO v2, official LEGO v3, and Pybricks v4.0.1 ARM binaries each executed 2,000 instructions from their genuine `0x08008000` vector table and remained in mapped flash. This proves instruction execution only; original/current protected images and deeper milestones remain. |
| 2026-09-06 | C5.1/C8.3 (real-payload build and protected boot) | In progress | Installed the pinned NuttX Kconfig tools locally and completed the unchanged protected production build outside Docker using the real ignored 10,211-byte/162-action TI package. Outputs are `nuttx.bin` 220,608 bytes (`32f93816...2ce`) and `nuttx_user.bin` 461,012 bytes (`8f8c8fe6...d20`); neither was committed or uploaded. The real pair executed in Renode from reset through `nx_start`, `board_late_initialize`, and entry to `stm32_bringup`, with its protected userspace descriptor present at `0x08080000`. It does not yet reach `nsh_main`; synchronous board peripheral modeling is the next C8.4 boundary. Physical execution remains required to complete C5.1. |
| 2026-09-06 | C8.4 (protected boundary isolation) | In progress | Added a separately labeled diagnostic gate that executes the same real kernel/user images, returns from `stm32_bringup` at a Renode CPU hook without patching either image, and proves the protected transition through `nsh_main` and the real `btsensor_main` entry from ROMFS `rcS`. The unchanged-image gate remains separate and stops only at actual board bring-up; replacing this broad isolation hook with peripheral models remains C8.4. |
| 2026-09-06 | C8.4 (minimal board stubs) | In progress | Narrowed the broad isolation to the first concrete missing device set. The real image now runs all of `stm32_bringup`; only LSM6DSL initialization, W25Q256 initialization, and TLC5955 initialization/update are hooked as deterministic absent devices. It then reaches real `nsh_main` and `btsensor_main`. Replacing these function-boundary stubs with register/device models and continuing daemon execution remain. |
| 2026-09-06 | C8.3 (five-target execution matrix) | Complete | Rebuilt original `owhinata/spike-nx` at pinned commit `00524ea...abe6` in an ignored detached worktree and staged its protected kernel (`221,180` bytes, `31852ec0...77b0`) and user image (`401,192` bytes, `fcabc6e4...8c7`). The full Renode suite passes for that pair and the current real-TI protected pair. Together with the earlier hash-verified official LEGO v2/v3 and Pybricks v4.0.1 runs, all five targets now execute actual ARM instructions from their genuine vector tables. This is bounded instruction/symbol evidence, not hardware compatibility evidence. |
| 2026-09-06 | C8.6 (private emulator CI) | Complete | Extended the private, manually dispatched protected build gate to install checksum-pinned Renode, stage only the current redistributable kernel/userspace pair built with the nonfunctional synthetic service-pack reservation, and run its reset/bring-up, protected-userspace-isolation, and narrow board-stub suites. Remote run `34055016271` passed all build, budget, Bluetooth-host, and Renode steps in 5m02s. No firmware, restricted package, or Renode result is uploaded. The complete five-target matrix remains local because the official, original spike-nx, and Pybricks inputs are private or mixed-license. |
| 2026-09-06 | Brickwright simulator (Pybricks identity) | Complete | Audited and pushed `CrispStrobe/brickwright-lite` commit `1d000ac61` on `feat/spike-firmware-simulator`. The virtual-hub registry and panel now distinguish LEGO legacy v2 (Classic), official v3 (LEGO-compatible BLE), Brickwright (both), and Pybricks (render/reference only). Pybricks deliberately advertises neither existing transport because its BLE service/protocol is not implemented. Live target switching updates BLE services; all 12 relevant virtual-SPIKE tests pass sequentially. |
| 2026-09-06 | C8.4 (register-level board models) | In progress | Added MIT Renode models for the LSM6DS3TR-C on I2C2, W25Q256JV on SPI2/PB12, and TLC5955 on SPI1. An audited no-function-hook run of the unchanged real-TI image completes the modeled IMU and flash initialization and reaches `tlc5955_initialize`. It then stops inside the display's SPI1 block transfer because Renode 1.16.1 does not complete this board's SPI/DMA transaction; unchanged userspace is not yet claimed. The separately labeled five-function diagnostic still reaches `nsh_main` and `btsensor_main`. |
| 2026-09-06 | C8.5 (lawful virtual-HCI seam) | In progress | Added an Apache-2.0 TCP/H4 controller bridge around the existing transport-neutral virtual HCI. Its explicit simulation-only policy acknowledges vendor opcodes without parsing, retaining, interpreting, or executing their parameters. Fragmented socket, vendor, reset, address, and virtual-controller tests pass. With the unchanged real-TI image, the audited Renode diagnostic reaches `physical_open`, `physical_load_firmware`, `ti_bts_execute`, and first `init_send`; stock Renode still lacks USART2 DMA1 S6/ch4 TX and S7/ch6 RX request coupling, so the physical write cannot yet reach `physical_start_host`. |
| 2026-09-06 | C4.2/C6.3 (delayed-work lifetime) | Complete | Remote emulator CI run `34056312743` exposed a timing-dependent host-link segfault on its first attempt (the rerun passed). Audit found `k_work_cancel_delayable_sync()` could return while a detached timer still retained an embedded work pointer. Sync cancellation now wakes and drains matching timer registrations before object reuse; a regression destroys/reinitializes the same storage immediately after cancellation. Ten audit repetitions plus 21 delegated focused runs passed, and 45 host-link executions produced no recurrence of the use-after-free crash. Separate pre-existing peer-ACL timeout flakiness remains to diagnose. |
| 2026-09-06 | Integrated private gate (`81d78d9`) | Complete | Remote run `34057171518` passed the protected build, budgets, host Bluetooth harness with the delayed-work lifetime fix, pinned Renode board-model matrix, and standalone lawful virtual-HCI bridge. No binary or emulator result was uploaded. |
| 2026-09-07 | C8.4/C8.5 (custom Renode DMA integration) | In progress | Forked Renode and Infrastructure privately under `CrispStrobe`, added generic MIT STM32 DMA/SPI/UART changes with 15 passing focused tests and a green private CI gate, and wired SPI1, SPI2, and USART2 board request lines. The custom build passes the LEGO v2/v3, Pybricks, original spike-nx, and Brickwright bounded gates. The unchanged Brickwright image completes SPI2 flash DMA, reaches TLC5955 initialization, consumes the opaque TI service-pack stream via the external H4 responder, and reaches `physical_start_host`. It then enters NuttX `_assert` before `bt_enable()` returns, so unchanged userspace and final host-start completion remain open. |
| 2026-09-07 | C8.5 (protected net-buffer initialization) | Complete | The post-host-start reset was traced through `arm_memfault` to `net_buf_alloc_fixed`: `hci_cmd_pool` was valid at `0x20024a84`, but its `alloc` initializer was zero and the saved fault was a precise read at `0x00000008` (`CFSR=0x82`). The orphan `net_buf_pool` output section began exactly at `_edata`, outside NuttX's protected userspace data-copy range. The board linker script now keeps the iterable pool table inside `.data`, and the resource gate fails closed unless `_sdata <= __start_net_buf_pool < __stop_net_buf_pool <= _edata`. A real-payload ARM rebuild places the non-empty range at `0x200248a4..0x20024cc4`; the custom-Renode HCI gate now passes through `bt_enable()` into `settings_load()` and onward to `brickwright_hub_transport_register()`. |
| 2026-09-07 | C8.5 (decoded virtual-HCI diagnostics) | Complete | The external Apache-2.0 bridge's opt-in trace now records every socket chunk in hexadecimal and decodes complete H4 command/event headers, including opcode and status for Command Complete/Status events. Tracing occurs before controller dispatch so request/response order is unambiguous. The socket regression covers fragmented vendor bootstrap acknowledgement, Reset, and Read BD_ADDR and asserts the decoded trace without interpreting vendor parameters. |
| 2026-09-07 | C4.3/C8.5 (daemon-ready emulation gate) | Complete | Refactored the daemon's blocking stop wait into the named `daemon_wait_for_stop` boundary, preserving EINTR behavior and providing a stable semantic milestone only reached after services start and `btsensor_transport_start()` succeeds. The real-payload custom-Renode gate now crosses the opaque TI stream, host enable, settings load, hub-transport registration, and this daemon-ready boundary. The protected ARM rebuild, resource/layout gate, neutral ARM compile, standalone HCI bridge test, and extended Renode test pass. Simulated peer connect/data/disconnect remains separate from daemon readiness. |
| 2026-09-07 | C8.6 (stock/custom platform split) | Complete | Remote baseline run `34089427905` passed the protected build, linker/resource checks, and host harness but correctly failed when stock Renode parsed custom-only UART `DMATransmit` wiring. The shared stock-compatible platform now retains memory and board-device models, while `spike-prime-custom-dma.repl` layers the fork-only request lines for the HCI gate. Locally, all five protected stock-Renode cases pass or intentionally skip HCI, and the custom-fork real-payload gate reaches daemon-ready. |

## Current next action

Continue C8.4 by replacing the remaining board-function hooks with deterministic
bus-level behavior and extend the protected gate from daemon-ready through
simulated peer link events. In parallel, finish coherent full IMU/sensor records,
encoder-completed degree moves, the explicit stall/capability policy, and
cold-restart bond reuse, then repeat the protected resource gate. Physical
C5/C6.4 validation resumes only when a hub is available; no simulation result
may close those hardware checkpoints.
