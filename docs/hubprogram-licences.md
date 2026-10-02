# Full firmware component licences

The simulator runner, upload protocol, motor controller and NuttX MicroPython
port in `apps/hubprogram` are newly authored under BSD-3-Clause, with the full
text in `apps/hubprogram/LICENSE`. Their copyright attribution is to
Brickwright contributors. The simulation input collector explicitly includes
`apps/hubprogram/micropython/brickwright_module.c`: embed build rules do not
emit its compiler dependency file. Earlier inventories omitted that authored
wrapper; the six-port refresh adds only this BSD-3-Clause source input.

The embedded interpreter comes from MicroPython v1.26.1 at
`647c8b96cae7e202c7a020395b7cfe65e5b8ce04`. Its core, embed port and GC helper
retain MIT notices and `third_party/micropython-embed/LICENSE`. The generation
recipe and configuration are recorded in that directory's `UPSTREAM.txt`.
The default embed console implementation is retained in that source package;
our application links its own bounded output adapter instead.

The retained firmware repository has its MIT `LICENSE`. Individual retained
source notices remain in place. NuttX and its applications retain their
Apache-2.0 licence and NuttX `NOTICE`. The retained Zephyr Bluetooth host
package has its Apache-2.0 `third_party/zephyr-host/upstream/LICENSE`, together
with individual source notices. The simulation build does not import a local
TI service-pack payload; its radio path is not a qualified BLE transport.

Renode's retained models have MIT notices and `licenses/MIT.txt`; new
Brickwright electrical-port and display-clock models have BSD-3-Clause
headers. The model stager preserves these source notices and includes both
licence texts. Firmware packaging must retain the dependency licence and
notice files alongside the source-built kernel and userspace images.

Original LEGO firmware is neither a dependency of this runner nor a packaged
asset. Optional local-image testing is separate from this licence inventory.

The empty simulation-flash generator in `tools/make_simulation_littlefs_seed.py`
and `tools/format_simulation_littlefs.c` is authored BSD-3-Clause, copyright
2026 Brickwright contributors. It compiles the already reviewed, NuttX-patched
LittleFS v2.5.1 `lfs.c` and `lfs_util.c` through their public API, without
changing those sources. LittleFS retains BSD-3-Clause, copyright 2022 the
littlefs authors and 2017 Arm Limited. Preserve
`nuttx/fs/littlefs/littlefs/LICENSE.md` alongside packaged firmware and any
redistributed formatter binary; its exact hash is in the simulation notice
inventory. The generated empty filesystem contains filesystem metadata,
not an imported firmware image. This host tool adds no firmware dependencies.

The exact retained LittleFS grant is also tracked at
[`licenses/LittleFS-BSD-3-Clause.txt`](../licenses/LittleFS-BSD-3-Clause.txt).
Source-only checks pin this copy so notice verification does not require an
initialized NuttX dependency. It reproduces the original
`nuttx/fs/littlefs/littlefs/LICENSE.md` bytes and copyright notices unchanged.
Configured firmware source and image fingerprints remain unchanged.
