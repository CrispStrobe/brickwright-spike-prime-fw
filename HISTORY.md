# Project history

This concise record lists accepted milestones. Detailed evidence remains in Git
and CI; pending work belongs in `PLAN.md`.

## Public permissive baseline

- Created a parentless public snapshot from
  `owhinata/spike-nx@00524ea5464bddb46c852967e382f8f6b073abe6`.
- Removed BTstack, firmware dumps, build products, and obsolete adapters from
  the public source graph.
- Isolated the exact CC2564C v1.5 service pack and TI licence as a hash-enforced,
  TI-device-only binary exception.
- Added simulation-only, no-artifact, English, source, workflow, documentation,
  resource, and service-pack policy gates.

## Protocol and Brickwright integration

- Specified the neutral hub, Classic RFCOMM/SPP, and FD02 BLE contracts.
- Added permissive C/JavaScript codecs and adverse-stream fixtures.
- Implemented virtual Classic/BLE transports over one hub state, with firmware
  profiles and rendered ports, devices, motors, sensors, matrix, battery, and IMU.

## Permissive Bluetooth host

- Imported a hash-pinned Apache-2.0 Zephyr 4.4.1 host selection and implemented
  its NuttX OS, buffer, crypto, settings, logging, and H4 compatibility seams.
- Exercised SDP/RFCOMM, ATT/GATT, legacy SMP, ACL flow control, and connection
  lifecycles against a deterministic native controller.
- Replaced the active daemon with the transport-neutral host implementation.
- Added host-side eHCILL and byte-preserving opaque BTS streaming without
  parsing or modifying TI vendor commands.

## Firmware and simulation

- Exposed the permissive dual-mode HCI model through a dedicated Renode firmware
  profile; it keeps the physical radio off and removes the TI payload from that
  profile's build graph while preserving the hardware profile unchanged.
- Routed bounded motor, display, sound, battery, sensor, and telemetry operations
  through the neutral daemon with ownership and disconnect-safe motor shutdown.
- Established protected memory gates and deterministic host/ARM tests.
- Added SPIKE Prime Renode targets for LEGO v2/v3, spike-nx, Pybricks, and
  Brickwright plus deterministic TLC5955, IMU, flash, DMA/SPI/UART, and H4 seams.
- The unchanged Brickwright image reaches host enable, settings load, transport
  registration, and daemon readiness.
- Added a SPIKE Essential platform skeleton and local hash-manifest loaders.

## Documentation and provenance

- Converted maintained documentation to English and enforced it in CI.
- Recorded protocol, TI, Pybricks/PBIO, other-hub, source-closure, Zephyr-host,
  resource, and provenance boundaries.
- Audited the first complete protected-build trace. It contains maps and 23
  depfiles but omitted descriptor duplication needed to resolve one `find`
  traversal, so no unverified source was vendored. The parser now handles
  pre-parent `vfork` events and removed intermediate working directories; a
  structured capture auditor records the remaining recapture requirement.
- Rebuilt a clean copied source tree successfully under a descriptor-complete
  trace. The parser resolved 4,060,664 lines and 6,121 candidate inputs and now
  excludes proved generated writes and directory traversal. The audit remains
  incomplete for 355 paths requiring classification, so none was vendored by
  inference.
- Completed the capture classification: renamed generated products retain their
  creation proof, descriptor aliases are not files, staged Mbed TLS inputs use a
  declared source root, and every remaining non-file is named by kind. The
  recapture audit is ready; source declaration and offline fixed-point builds
  remain separate gates.
- Established a pinned Arm GNU Toolchain boundary with a digest-locked release,
  immutable upstream revisions and licence evidence, an isolated build
  environment, and separate exact-file policy for linked GCC/newlib inputs.
- Proved two clean serial protected builds byte-identical under the pinned ARM
  boundary. Parallel builds remain excluded because application archive member
  ordering changed the userspace image; hashes and the negative control are in
  `evidence/source-closure/fixed-point-build.json`.
- Added deterministic link-input evidence that joins explicit reviewed runtime
  declarations to exact map paths and verifies selected archive membership with
  the pinned Arm archiver, without suffix-based licence classification.
- Measured the protected build fixed point: parallel application archive updates
  reorder user objects, while two clean serial builds produced identical kernel
  and user images and maps. Only hashes are recorded; offline source declarations
  remain a separate gate.
- Locked the exact staged LittleFS, composed Mbed TLS, patched newlib/libm, and
  Kconfig frontend inputs and added a fail-closed verifier for their tree,
  archive, and patch hashes. Link evidence now expands response files and
  cross-checks explicit toolchain artifacts and map outputs against the maps.
- Captured one same-generation compiler, archiver, preprocessor, and linker
  graph; retained removed linker-script bytes by hash; and generated and
  verified the 902-file permissive source manifest, 145 generated-input records,
  SPDX 2.3 SBOM, and host-path-free link evidence. A copied source-only tree
  contains 1,047 files; its offline build correctly fails closed because the
  separately traced build-system Makefiles have not yet joined the closure.
- Audited the protected userspace evidence and found that `User.map` was an
  `nm` symbol listing, so it could not select `libapps` archive members. The
  protected link now emits a separate GNU linker map as `nuttx_user.map`; the
  old symbol listing remains available for compatibility.
