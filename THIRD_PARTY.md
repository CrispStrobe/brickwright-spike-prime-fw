# Third-party components

This inventory describes the public source snapshot. It does not relicense any
component.

| Component | Pin | Licence in this distribution | Treatment |
|---|---|---|---|
| spike-nx baseline | `owhinata/spike-nx@00524ea5464bddb46c852967e382f8f6b073abe6` | MIT | Project baseline; root `LICENSE`. |
| NuttX | `owhinata/nuttx@a67efb31cf4f236e456882589b91862f04594528` | Primarily Apache-2.0; optional files vary | External gitlink. Selected inputs include Apache-2.0 and BSD-3-Clause files, including the tickless timer. Its own licence/NOTICE and per-file grants control. |
| NuttX Apps | `owhinata/nuttx-apps@55f0bc216565ccab8dee600a88f4485c7693bf8b` | Primarily Apache-2.0; optional files vary | External gitlink. Only the configured application closure is linked. Its own licence/NOTICE controls. |
| Reviewed NuttX/NuttX Apps backports | Source SHAs, authors and adaptations in [policy/nuttx-backports.json](policy/nuttx-backports.json) | Apache-2.0 and BSD-3-Clause, per file | Hash-checked patches on the existing dependency pins; original ASF headers/NOTICE preserved. Full grants in `licenses/Apache-2.0.txt` and `licenses/NuttX-Tickless-BSD-3-Clause.txt`. |
| Zephyr Bluetooth host selection | Zephyr `v4.4.1`, exact commit in `third_party/zephyr-host/manifest.json` | Apache-2.0 | Vendored, hash-pinned selection; upstream licence retained and local patch recorded. |
| Pybricks-derived/reference code | Audited baseline reference `101c6babb592148bda9a8fd912b7953c7d561c0a`; present at all 46 current-path introductions in spike-nx | MIT and BSD-3-Clause; UART selects MIT from MIT OR GPL-2.0-only | 46 local source/reference files mapped in `policy/pybricks-reuse.json`. Original Pybricks, LEGO and David Lechner notices retained; full grants in `licenses/`. Per-path history in `policy/source-origin-review.json`; pin availability does not establish every external reading event. |
| Fusion inclination-feedback adapters | `xioTechnologies/Fusion@a8d7224f36a0ec82345ef49a3db50e65f8d3bab8` | MIT, Copyright (c) 2021 x-io Technologies; adaptations Copyright (c) 2026 Brickwright contributors | Replaces the inherited host and firmware gradient-descent bodies. Reduced gravity-vector feedback adapters with exponential quaternion integration; historical caller names retained. Pin, hashes and changes in `policy/orientation-filter.json`; full grant in `licenses/Fusion-MIT.txt`. Retired revisions remain uncleared private evidence; the advertised-history cleanup is recorded in `policy/public-history-review.json`. |
| Embedded MicroPython | `micropython/micropython@647c8b96cae7e202c7a020395b7cfe65e5b8ce04` (v1.26.1) | MIT; one local BSD-3-Clause replacement | Core/embed selection and generated headers inventoried in `policy/micropython-embed.json`. The Stack Overflow integer-width formula is removed. Upstream notices and local BSD grant retained. |
| Mbed TLS crypto | `107ea89daaefb9867ea9121002fbbdf926780e98` (3.6.2), fetched archives hash-pinned | Apache-2.0 selected from Apache-2.0 OR GPL-2.0-or-later | Compiled into the Zephyr host archive. Source/header evidence survives temporary-source cleanup; grant retained in `licenses/MbedTLS-3.6.2-LICENSE.txt`. |
| newlib maths and toolchain headers | libm 4.3.0.20230120 plus NuttX patches; toolchain headers from libnewlib-dev 4.4.0.20231231-2 | File-level BSD/permissive/public-domain grants; NuttX integration changes Apache-2.0 | Inputs, original grants and default notices recorded in the simulation inventory and notice bundle. Other target-specific notices in the aggregate do not imply those targets are linked. |
| GNU compiler runtime | gcc-arm-none-eabi `15:13.2.rel1-2`; runtime archive hash and 20 selected member names in the simulation inventory | GPL-3.0-or-later WITH GCC-exception-3.1 | Explicit runtime exception, with ordinary GCC compilation. Full GPL and exception texts retained; no plain-GPL or MIT reclassification. |
| TI CC2564C service pack 1.5 | TI commit `3aa1d75f3c2ae77f6e4d36194e3d281b899ab149`; SHA-256 `646723c01de351eaf9c6b6b33f4f0dac9567b948a2e93daed9da7a896b6e1b0e` | TI Text File License | **Absent from the current tree and reviewed advertised history; retained only in private historical evidence.** The hardware profile fetches it from TI's git at build time into ignored `.local/ti/`, verified by SHA-256; a mismatch is refused. Both TI-free simulation profiles exclude it from the build graph. `tools/check_ti_free_image.py` rejects known payload fingerprints and service-pack build references; it does not prove the absence of arbitrary transformed fragments. |

The current tree includes no TI service pack, LEGO firmware dump, official
SPIKE firmware image, BTstack source or BTstack binary. This statement does
not describe every historical commit. `policy/ti-service-pack-fingerprint.json`
holds only digests of the service pack's 256-byte chunks, used by the
simulation gate; it contains no service-pack bytes. Simulator inputs for official firmware remain
user-supplied local files and are never CI artifacts.

`tools/check_reuse_licenses.py` verifies tracked reuse notices, allowed SPDX
expressions and pinned embedded-interpreter inputs during CI and builds.
The configured simulation builds are separately recorded in
`policy/simulation-firmware-inputs.json` and
`policy/simulation-hci-firmware-inputs.json`: each records 3,246 conservative
source/header/linker inputs, its selected archive-member sets and the direct
startup object. The
superset includes compiled or inventoried inputs whose code may not survive
linking. `licenses/Simulation-Firmware-NOTICES.txt` bundles their grants and
attribution. `tools/check_simulation_firmware.sh` checks source/config/runtime
hashes, linker-selected member sets and TI exclusion after simulation builds.
These reviews cover the two simulation profiles and recorded toolchain; other configurations and changes
require review. These checks verify declared grants and hashes; the broader
source-origin review identified unresolved inherited filter provenance. Both
current implementations and the recorded build have now been replaced and tested;
the approved cleanup retires that ancestry and 19 non-main public branch refs.
Their private archival preservation does not relicense those revisions.
See `policy/source-origin-review.json` and `policy/public-history-review.json`. Hardware images containing the fetched
TI service pack remain subject to TI restrictions; no exclusively permissive
licence claim is made for those images.


## Host-only simulated Bluetooth air

The peer tests use the existing Renode fork's
[`tools/bw-air` at the qualified runtime pin](https://github.com/CrispStrobe/renode-spike-prime/tree/e0166acb028b162e972458f31d76cdb7dcdc518d/tools/bw-air),
retaining its MIT/Apache-2.0 grants and author notices. This repository does
not vendor a second copy. `tools/bluetooth-air-requirements.txt` fixes the 17
Python dependencies used by the host test environment; these packages enter
neither ARM firmware nor WASM. Their upstream notices remain in the installed
packages. The versions, declared grants and installed notice hashes are in
`policy/bluetooth-air-host-inputs.json` and are checked before the peer gate.

Bumble and importlib-resources use Apache-2.0; websockets, click, pycparser,
prompt-toolkit, pyusb, pyserial and pyserial-asyncio use BSD-3-Clause;
platformdirs, pyee and wcwidth use MIT; cffi declares MIT-0; typing-extensions
uses PSF-2.0. Cryptography offers Apache-2.0 or BSD-3-Clause. The libusb-package
wrapper uses Apache-2.0 and bundles LGPL libusb; libusb1 uses
LGPL-2.1-or-later. Its accompanying GPL `COPYING` text is part of the LGPL
licence distribution. Pyserial 3.5's wheel omits a standalone licence file;
its source headers and matching source-distribution licence declare BSD-3-Clause.
This host-only record does not claim an exhaustive audit of every bundled
binary dependency. Python and pip are supplied by the host runner separately.
