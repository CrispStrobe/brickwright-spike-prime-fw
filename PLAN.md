# Brickwright SPIKE Prime firmware plan

This file is the ordered queue for unfinished work. Completed work belongs in
`HISTORY.md`; current interfaces belong in their contract documents.

## Operating rules

- Work in a dedicated worktree and feature branch based on the latest remote
  target branch. Never edit a shared primary checkout.
- Complete tasks in the order below unless two tasks are explicitly independent.
  Commit and push each accepted task before starting its dependent.
- Preserve unrelated changes and dependency pins.
- Project-owned and vendored source must be MIT, Apache-2.0, BSD-3-Clause, or an
  explicitly approved comparable permissive licence. GPL-family, AGPL,
  noncommercial, and source-incompatible code are forbidden.
- The exact, unmodified CC2564C service pack and adjacent TI licence are the
  only approved restricted exception. Do not inspect vendor parameters, modify
  the payload, or describe it as project-licensed code.
- Official LEGO and packaged Pybricks images are local, ignored test inputs.
  Never fetch, commit, log, cache, or upload them.
- Simulation is not hardware evidence. Do not flash a hub, publish a flashable
  artifact, or add physical-installation instructions while `SAFETY.md` applies.
- Move accepted task summaries to `HISTORY.md`; never add completion logs here.

## Stable contracts

- `protocol/hub-contract.schema.json` is the transport-neutral hub API.
- `docs/en/project/classic-protocol.md` defines legacy RFCOMM/SPP.
- `docs/en/project/ble-protocol.md` defines the FD02 BLE protocol.
- `docs/en/project/ti-service-pack.md` defines the opaque TI boundary.
- `docs/en/project/source-closure-tooling.md` defines closure evidence.
- `docs/en/project/resource-budgets.md` defines target memory limits.
- Port state changes carry attachment generations; stale operations fail.
- A disconnect places every motor owned by that transport in its defined safe
  state. Simulator and firmware share byte-level fixtures where practical.

## Ordered simulation roadmap

### S1 — Configured permissive source closure

Build a minimal reproducible source tree for the protected image.

1. Capture successful build inputs with per-process working directories,
   complete descriptor lifecycles, compiler depfiles, the link map, and archive
   membership. The accepted capture contract and evidence are recorded in
   `docs/en/project/source-closure-tooling.md` and `HISTORY.md`.
2. Declare immutable roots, pins, patch policy, licence overrides, and generated
   inputs; generate the deterministic manifest, SPDX 2.3 SBOM, and link evidence.
   Derive runtime artifacts from the captured linker command, maps, and archive
   membership, and cross-check all three sources before accepting the evidence.
3. Replace broad NuttX/NuttX Apps gitlinks with only the verified closure.
4. Rebuild offline until no undeclared input is consumed. Closure builds remain
   serial until archive creation is made deterministically parallel.

Pending closure details: extend the verified final-linked source closure with
the traced build-system inputs (Makefiles, configuration generators, and host
tools) needed to configure the copied tree, then build that copied closure twice
offline and prove both builds consume no undeclared input. Serial archive
construction remains required until member collection is canonicalized.

Acceptance: two clean offline builds have identical images/manifests; every
linked input has allowed licensing and immutable provenance; the verifier rejects
undeclared files, escapes, hash drift, ambiguous paths, and unknown/compound
licences; all policy, documentation, and resource checks pass.

### S2 — Reproducible public CI

Depends on S1. Pin actions, containers, tools, and source inputs by immutable
digest; use read-only permissions and no network after acquisition; build only
redistributable inputs; publish no firmware artifacts.

Acceptance: two clean hosted runs report identical hashes; workflow policy proves
least privilege and immutable pins; logs, caches, and artifacts contain no
restricted or user-supplied image.

### S3 — Unchanged protected-image bring-up

Depends on S2. Work in the public Renode fork/infrastructure model. Replace every
remaining synchronous function hook with deterministic bus-level clock, DMA,
SPI, UART, I2C, interrupt, and reset behavior. Firmware may add observation
symbols but may not bypass production paths.

Acceptance: the unchanged image reaches reset, kernel start, protected userspace,
board bring-up, Bluetooth host enable, transport registration, and daemon
readiness; removing any required model fails the test; diagnostic hooks are
reported separately and never count as unchanged execution.

### S4 — Brick peripheral models

Depends on S3. HCI and LPF2 work may proceed independently.

1. Implement a transport-neutral H4 controller service with deterministic GAP,
   L2CAP, RFCOMM, ATT, GATT, SMP, connections, credits, and faults. Vendor
   commands receive opaque policy-controlled acknowledgements only.
2. Model six LPF2 ports: identification, UART negotiation, sensor modes/data,
   motor commands, encoder motion, load, stall, detach, and generations.
3. Complete observable TLC5955, IMU timing/FIFO/interrupt, W25Q256 persistence,
   buttons, center LED, sound/DMA, battery, charger, power, reset, and shutdown.

Acceptance: model tests cover registers, timing, interrupts, reset, bounds, and
malformed transactions; one motor and sensor complete attach through detach;
snapshots expose every modeled device; no model executes or derives TI firmware.

### S5 — Firmware feature and radio conformance

Depends on S4. Complete coherent sensor/IMU records, encoder-completed degree
moves, stall policy, display, buttons/LED, sound, battery, storage, and safe
update behavior. Complete BLE GATT/SMP, bond reload, and simultaneous Classic/BLE
through the actual ARM image. Enforce bounded queues, timers, stacks, memory,
latency, and backpressure.

Acceptance: shared malformed/fragmented/coalesced/reconnect fixtures pass natively
and through ARM; both transports operate concurrently; disconnect, timeout, stale
generation, and exhaustion reach defined safe states; memory budgets pass.

### S6 — Five-family scenario matrix

Depends on S5. Run official LEGO v2, official LEGO v3, original spike-nx,
Pybricks, and Brickwright with target-specific manifests and milestones.

Acceptance: every available image passes vectors, boot milestones, one interactive
peripheral scenario, persistence, disconnect, reset, and corrupt-input tests;
unavailable opaque inputs skip explicitly; machine output distinguishes full
scenarios, bounded progress, diagnostic hooks, and unsupported behavior.

### S7 — Brickwright device panel

Depends on stable S4 snapshots; may overlap S5/S6. Expose firmware identity,
transport, boot state, ports A–F, devices, motors, sensors, display, IMU, battery,
sound, and faults through a versioned simulator-state interface. Never infer a
profile from a filename.

Acceptance: profile selection changes only declared capability/routing; rendered
state follows Renode during attach, command, telemetry, disconnect, and reset;
transport-only virtual-hub tests remain green.

### S8 — Fault, recovery, and soak gates

Depends on S5/S6. Inject UART loss, controller timeout, LPF2 detach, motor stall,
flash corruption/power loss, low battery, exhaustion, interrupt delay, daemon
restart, and repeated reset using fixed seeds and virtual time.

Acceptance: each fault has bounded recovery or an explicit terminal state; motors
reach safe state; resources do not grow without bound; repeated runs yield
identical state/event traces.

### S9 — Additional hubs

Depends on reusable S8 contracts. Target SPIKE Essential, then Technic/Control+,
City Hub, and BOOST Move Hub. RCX/H8 and EV3/AM1808 are separate architecture
projects. Use PBIO as a pinned behavioral oracle; import only individually
MIT-marked files after complete transitive closure approval.

Acceptance: each hub has a source-cited map, distinct profile, local manifest,
bounded boot proof, and explicit unsupported features before modeling begins.

## Hardware release gate

This gate is unavailable until S1–S8 pass and a maintainer authorizes physical
work. It requires sacrificial hardware, current-limited power, motor/port safe
states, battery/charger and update recovery, exact TI-payload verification,
Classic/BLE interoperability, fault/soak testing, legal review, and a recorded
go/no-go decision. Until then, `SAFETY.md` is authoritative.
