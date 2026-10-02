# TI CC2564C service pack

A physical CC2564C needs TI's initialization service pack after every power
cycle. TI licenses `TIInit_6.12.26.bts` (service pack 1.5) for use only with
TI devices and forbids reverse engineering, decompilation, and disassembly.

This repository does not redistribute it. Firmware is built in one of two
profiles.

## Simulation profile (`BOARD_CONFIG=simulation`)

`CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK=y` removes the service pack from the
build graph: no provider shim, no include path, no import rule. The firmware
keeps the complete physical controller path (chip reset, `/dev/ttyBT`, H4 over
USART2 DMA, the Zephyr host) and skips only the upload step, so the simulated
controller is addressed exactly as hardware would be, left in its ROM state at
the boot baud. The simulated controller answers standard HCI and, in this
profile's Renode gate, rejects vendor commands, so a stray upload would fail
visibly.

This profile keeps the boot path closer to hardware than an in-process virtual
controller would: every UART, DMA, and H4 step still executes. It is the only
profile that CI builds and runs.

`tools/check_ti_free_image.py` gates it. It scans every 256-byte window of each
image against `policy/ti-service-pack-fingerprint.json` (digests of the service
pack's 40 chunks; no service-pack bytes) and reports the chunk count. It also
fails if the verbose build log or dependency files name the service pack, the
importer, or `.local/ti/`, if `.config` does not select the profile, or if the
ELF defines the embedded-payload symbol. On the hardware-profile image it
reports 40/40 chunks and fails; on the simulation image it reports 0/40 and
passes.

## Hardware profile (`BOARD_CONFIG=usbnsh`)

The build runs `tools/import_ti_service_pack.py --from-ti`, which fetches the
service pack and TI's `LICENSE` from `https://git.ti.com/git/ti-bt/service-packs.git`
at commit `3aa1d75f3c2ae77f6e4d36194e3d281b899ab149`. It refuses the files
unless the service pack's SHA-256 is
`646723c01de351eaf9c6b6b33f4f0dac9567b948a2e93daed9da7a896b6e1b0e` and the
licence's is `21fd99ce784dc33b39ec0b4a383a9a9b8dafea261d73ad4548683c4eecd87f37`
(`policy/ti-service-packs.json`). To build offline, set
`BRICKWRIGHT_TI_SERVICE_PACK` to a local copy (a file, a directory, or a ZIP that
also contains TI's `LICENSE`); the same hashes apply.

The importer writes the unmodified file, its licence, and a byte-for-byte C
container below the ignored `.local/ti/cc2564c/`. It does not decode vendor
parameters. The resulting image is chip-restricted: it embeds TI's service
pack and may be used only with a TI CC2564C. Do not run it in a simulator and
do not redistribute it without TI's licence. The firmware remains
simulation-only under `SAFETY.md`, so no hardware image is published.

Source policy forbids the service pack and its licence in Git by path and by
hash.
