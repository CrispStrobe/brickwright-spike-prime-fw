# Brickwright SPIKE Prime firmware

Experimental firmware for the LEGO SPIKE Prime hub, developed for the
Brickwright Renode simulator. This is a **work in progress**, derived from
[spike-nx](https://github.com/owhinata/spike-nx), using NuttX as its operating
system and incorporating adapted or referenced Pybricks robotics code.

> **WARNING — SIMULATION-ONLY WORK IN PROGRESS**
>
> This firmware has not completed real-hardware electrical, motor-safety,
> power-loss, thermal, radio, recovery or long-duration validation.
> **Do not flash** images from this repository onto a physical hub or other
> real silicon. Simulator and unit-test results do not establish hardware
> safety. See [SAFETY.md](SAFETY.md).

## Origins and architecture

This project builds on substantial work by upstream projects and their
contributors:

- **[spike-nx](https://github.com/owhinata/spike-nx)** supplies the original
  SPIKE Prime NuttX board support, drivers and robotics applications. Our
  source snapshot derives from
  [commit `00524ea5464bddb46c852967e382f8f6b073abe6`](https://github.com/owhinata/spike-nx/commit/00524ea5464bddb46c852967e382f8f6b073abe6).
  Its MIT copyright notice for KatsumiOuwa is retained in [LICENSE](LICENSE).
- **[Apache NuttX](https://github.com/apache/nuttx)** supplies the operating
  system, scheduling, device framework and system services. This repository
  pins the [owhinata NuttX fork](https://github.com/owhinata/nuttx) and
  [NuttX Apps fork](https://github.com/owhinata/nuttx-apps) as Git submodules.
  These are primarily Apache-2.0 projects, with file-level and optional
  component licences that must be considered for each build.
- **[Pybricks](https://github.com/pybricks/pybricks-micropython)** is the source
  or reference for portions of motor/drivebase control, IMU processing and
  hub/device behaviour inherited through spike-nx. All 46 currently
  inventoried files existed in that upstream baseline; 45 were
  byte-identical before our edits. This is acknowledged
  source/reference reuse under MIT and BSD-3-Clause, including original
  Pybricks, LEGO System A/S and David Lechner notices.
- **[MicroPython](https://github.com/micropython/micropython)** supplies the
  embedded Python interpreter. A selected core/embed tree from v1.26.1 is
  vendored under [third_party/micropython-embed](third_party/micropython-embed).
- **[Zephyr](https://github.com/zephyrproject-rtos/zephyr)** supplies the
  selected Bluetooth host code, with a NuttX compatibility layer. Its
  Apache-2.0 source selection and modifications are recorded in the
  [host manifest](third_party/zephyr-host/manifest.json).
- **Texas Instruments** supplies the CC2564C Bluetooth controller service
  pack used by the optional hardware build profile. Its restricted licence is
  separate from the source licences above; the payload is fetched at build
  time and is excluded from the simulation profile.

Brickwright changes add simulator integration, robot-program execution,
embedded Python integration and associated checks.

## Licences and third-party notices

The root MIT licence from upstream spike-nx, and for our code, does not relicense third-party components or generated
firmware images. Preserve each component's copyright and licence notices.

The [broader source/history review](docs/project/source-origin-review.md)
identified inherited filter provenance, historical TI payloads and older branch
snapshots without corrected grants. Both current filters have been replaced
with credited MIT Fusion adapters and tested in rebuilt firmware. The approved
[public history cleanup](docs/project/history-cleanup.md) starts `main`
from that tested snapshot and retires the 19 reviewed non-main branches.
The recorded findings are resolved for current source, the configured build
and advertised history. Optional targets, GitHub caches and other clones are
outside that review; this is no blanket guarantee about every possible origin.

- [LICENSE](LICENSE): the inherited spike-nx MIT grant.
- [NOTICE](NOTICE): project attribution and distribution notices.
- [THIRD_PARTY.md](THIRD_PARTY.md): component pins, licences and treatment.
- [Provenance inventory](docs/project/provenance.md): inherited origins,
  reuse evidence and remaining configured-build audit work.
- [Pybricks MIT grant](licenses/Pybricks-MIT.txt),
  [selected UART MIT grant](licenses/LEGO-UART-MIT.txt),
  [LEGO BSD-3-Clause notices](licenses/LEGO-BSD-3-Clause.txt), and
  [Brickwright BSD-3-Clause grant](licenses/Brickwright-BSD-3-Clause.txt).
- [Embedded MicroPython licence](third_party/micropython-embed/LICENSE) and
  [Zephyr host licence](third_party/zephyr-host/upstream/LICENSE).
- [NuttX licence](https://github.com/owhinata/nuttx/blob/a67efb31cf4f236e456882589b91862f04594528/LICENSE)
  and [NuttX Apps licence](https://github.com/owhinata/nuttx-apps/blob/55f0bc216565ccab8dee600a88f4485c7693bf8b/LICENSE),
  together with their own notices and individual source headers.

Machine-readable records cover [Pybricks reuse](policy/pybricks-reuse.json)
and the [embedded MicroPython selection](policy/micropython-embed.json),
plus the [replacement orientation adapters](policy/orientation-filter.json).
The [simulation build inventory](policy/simulation-firmware-inputs.json)
records reviewed compiler inputs, selected linked archive members and image
hashes. Its [redistribution notice bundle](licenses/Simulation-Firmware-NOTICES.txt)
retains the inventoried grants and attribution, including the
[Fusion MIT grant](licenses/Fusion-MIT.txt) for the replacement filters;
it does not retroactively license retired revisions. The compiler runtime uses GPLv3
with the [GCC Runtime Library Exception](licenses/GCC-Runtime-Exception-3.1.txt);
it is recorded under that licence, not relabelled MIT/BSD. Builds check the
reviewed source/configuration/runtime and linker input sets. Other configurations
or dependency changes require a new review. Hardware images that include
the TI service pack do not meet an exclusively permissive-licence policy.
See [the TI service-pack record](docs/project/ti-service-pack.md).

## Building for simulation

The build requires Git, Make and Docker. From a fresh checkout:

```sh
git submodule update --init nuttx nuttx-apps
make nuttx BOARD_CONFIG=simulation
```

The build applies the [reviewed NuttX backports](docs/project/nuttx-backports.md)
to the exact pinned dependencies and checks their source hashes. Keep the
patch series when reinitializing submodules. Use a clean build after changing
configuration; stale archive members in this baseline can survive an incremental build.

The simulation profile excludes the TI service pack. CI builds and runs
this profile; [the TI exclusion checker](tools/check_ti_free_image.py)
checks images and build references for service-pack material. No flashable
firmware is published while the hardware-validation gate remains open.

The default `make nuttx` profile is `BOARD_CONFIG=simulation`. The optional
`make nuttx BOARD_CONFIG=usbnsh` hardware profile fetches the TI service pack with a pinned commit and SHA-256 and produces a hardware
build subject to TI's terms. It remains unsupported for physical installation
at this experimental stage. Use the explicit simulation command above.

## Development documentation

- [Getting started](docs/en/development/getting-started.md)
- [Driver architecture](docs/en/drivers/architecture.md)
- [Firmware source reuse](docs/en/development/licence-reuse.md)
- [Simulator/hub contract](docs/project/hub-contract.md)
- [Development plan and recorded milestones](PLAN.md)
- [Japanese documentation](docs/ja/index.md)

The documentation includes inherited hardware workflows and historical
results. Those describe upstream work or development experiments; they do
not override this fork's simulation-only status.
