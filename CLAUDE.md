# SPIKE Prime Hub NuttX project

This repository develops a NuttX RTOS environment for the SPIKE Prime Hub.
Read `SAFETY.md` before proposing or running hardware operations. The current
public derivative is simulation-only and must not be flashed to real hardware.

## Development workflow

Keep changes small and repeat this cycle:

1. Implement one focused change.
2. Build it with `make` or perform a clean build when configuration changed.
3. Validate it in the supported Renode simulation.
4. Run the relevant automated tests and inspect logs.
5. Update the English documentation with the implementation.

For phase or architecture plans, run the `codex-review` skill before leaving
plan mode. A successful review updates `~/.claude/.plan-codex-reviewed` for two
hours. Skipping review for a trivial plan requires explicit user approval.

## Git and issue workflow

- Open an issue with a summary, reproduction steps for bugs, environment, and
  relevant notes.
- Work on a dedicated branch. Build and test before committing.
- Use focused commits and include the issue number where useful.
- Merge only after review and validation, then report the implemented changes,
  test evidence, and any remaining limitations on the issue.
- Never write to `apache/nuttx`, `apache/nuttx-apps`, or
  `pybricks/pybricks-micropython`. Those repositories are read-only references.

## Documentation

Maintained documentation is English-only and lives under `docs/en`:

- `hardware`: board overview, pins, peripherals, DMA, and IRQ allocation
- `drivers`: driver design and implementation status
- `development`: build, debugging, application, and protocol workflows
- `nuttx`: NuttX-specific port notes and upstream issues
- `testing`: validation specifications
- `usage`: user-facing procedures
- `project`: provenance, licensing, and protocol evidence

Build documentation with:

```bash
mkdocs build --strict
```

Use source links that point to stable upstream revisions when documenting
external code. Keep current truth separate from historical issue plans.

## Applications

Applications live in `apps/<name>` and normally contain source, a `CMakeLists`
file, and Kconfig metadata. Register a new application with the board snapshot
and add tests and documentation in the same change. Avoid duplicating driver
logic in applications.

## Build environment

The default board is `spike-prime-hub` with the `usbnsh` configuration.

```bash
make                         # configure and build
make nuttx-menuconfig        # edit Kconfig
make nuttx-savedefconfig     # save defconfig
make nuttx-clean             # retain .config
make nuttx-distclean         # remove .config too
make distclean               # remove build image and deinitialize submodules
```

NuttX and NuttX Apps are pinned submodules. Pybricks may be consulted as a
behavioral oracle, but copied code retains its own licensing obligations and
must not be assumed to be uniformly MIT licensed. See `THIRD_PARTY.md` and the
project provenance documentation before importing any implementation.

## Testing

Run source-policy, safety, documentation, host-unit, and focused subsystem
tests in proportion to the change. Hardware-dependent pytest cases use the
fixtures in `tests/conftest.py`; do not run them against physical hardware
while the simulation-only safety restriction is active.

When debugging, capture the exact command, expected result, actual result,
reproduction rate, configuration, and recent relevant commits. Check hardware
constraints in RM0430 and compare equivalent Pybricks behavior where relevant.

## Device and architecture terms

- Hub: SPIKE Prime Hub
- MCU: STM32F413VG, Cortex-M4F, up to 96 MHz
- RTOS: NuttX
- NSH: NuttShell
- External flash: W25Q256, 32 MiB SPI NOR
- Bluetooth controller: TI CC2564C

Treat timer, DMA, IRQ, GPIO, clock, radio, power, and motor assignments as
shared board resources. Consult `docs/en/hardware/dma-irq.md` and
`docs/en/hardware/pin-mapping.md` before changing them. A compiling driver is
not evidence that a peripheral feature exists on STM32F413; verify RM0430 and
provide simulation or hardware evidence appropriate to the safety policy.
