# Vendored TI CC2564C service pack

The CC2564C requires an initialization service pack after every power cycle.
This repository carries TI's exact, unmodified `TIInit_6.12.26.bts` v1.5 at
`third_party/ti-cc2564c/`, together with the byte-exact `LICENSE.ti` governing
it.

The service pack is not MIT, Apache, or BSD software. TI's terms permit
unmodified binary redistribution when the licence and copyright are preserved,
restrict use to TI devices, and prohibit reverse engineering, decompilation,
and disassembly. This project does not relicense it.

Source policy pins the TI commit `3aa1d75f3c2ae77f6e4d36194e3d281b899ab149`,
BTS SHA-256 `646723c01de351eaf9c6b6b33f4f0dac9567b948a2e93daed9da7a896b6e1b0e`,
and licence SHA-256
`21fd99ce784dc33b39ec0b4a383a9a9b8dafea261d73ad4548683c4eecd87f37`.

The build verifies these inputs and creates an ignored byte-for-byte C
container. Neither importer nor simulator decodes vendor parameters. Renode
may stream and acknowledge opaque HCI commands to test host control flow; it
does not execute or validate TI controller firmware.

CI may build and simulate the combined image ephemerally but publishes no
flashable artifact. The firmware remains simulation-only and must not be
installed on physical hardware until `SAFETY.md` and the hardware-validation
roadmap are completed.
