# Third-party components

This inventory describes the public source snapshot. It does not relicense any
component.

| Component | Pin | Licence in this distribution | Treatment |
|---|---|---|---|
| spike-nx baseline | `owhinata/spike-nx@00524ea5464bddb46c852967e382f8f6b073abe6` | MIT | Project baseline; root `LICENSE`. |
| NuttX | `owhinata/nuttx@a67efb31cf4f236e456882589b91862f04594528` | Primarily Apache-2.0; optional files vary | External gitlink. Optional BSD components are disabled in the target configuration. Its own licence/NOTICE controls. |
| NuttX Apps | `owhinata/nuttx-apps@55f0bc216565ccab8dee600a88f4485c7693bf8b` | Primarily Apache-2.0; optional files vary | External gitlink. Only the configured application closure is linked. Its own licence/NOTICE controls. |
| Zephyr Bluetooth host selection | Zephyr `v4.4.1`, exact commit in `third_party/zephyr-host/manifest.json` | Apache-2.0 | Vendored, hash-pinned selection; upstream licence retained and local patch recorded. |
| Pybricks-derived algorithms | Pybricks provenance recorded in affected files and project provenance | MIT | Adapted source/algorithms only; no Pybricks gitlink remains. |
| TI CC2564C service pack 1.5 | TI commit `3aa1d75f3c2ae77f6e4d36194e3d281b899ab149`; SHA-256 `646723c01de351eaf9c6b6b33f4f0dac9567b948a2e93daed9da7a896b6e1b0e` | TI Text File License | Exact unmodified binary plus adjacent `LICENSE.ti`; TI-device-only and no reverse engineering. Not permissively licensed source. |

No LEGO firmware dump, official SPIKE firmware image, BTstack source, or
BTstack binary is included. Simulator inputs for official firmware remain
user-supplied local files and are never CI artifacts.
