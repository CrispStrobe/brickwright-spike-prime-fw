# SPIKE Prime instruction-level simulation

This directory boots actual STM32 firmware images. It does not replace the
existing transport/protocol simulator in Brickwright; the two gates answer
different questions.

The shared platform starts from Renode's STM32F4 peripheral model and adds the
SPIKE Prime memory map: the upper 64 KiB of the STM32F413VG's 320-KiB SRAM and
the 32-MiB W25Q256 address window. Target loaders always use the real vector
table at `0x08008000`.

## Target matrix

| target | local input | load form | first proof |
|---|---|---|---|
| `lego-v2` | user-supplied official legacy image | raw at `0x08008000` | valid vectors and PC leaves reset handler |
| `lego-v3` | user-supplied official modern image | raw at `0x08008000` | valid vectors and PC leaves reset handler |
| `spike-nx` | rebuilt from upstream commit `00524ea5464bddb46c852967e382f8f6b073abe6` | protected kernel and user images | symbol milestones |
| `brickwright` | rebuilt from this branch | protected kernel and user images | symbol milestones through daemon start |
| `pybricks` | user-supplied Pybricks release package | `firmware-base.bin` at `0x08008000` | valid vectors and PC leaves reset handler |

Official LEGO and packaged Pybricks binaries are separately licensed inputs and
remain under ignored `.local/firmware-images/`. They are neither copied into
this repository nor uploaded by CI. Users must lawfully obtain and stage their
own files; the target manifest verifies known hashes before execution.

The public [gpdaniels/spike-prime snapshot](https://github.com/gpdaniels/spike-prime/tree/0b0c11f89cca61cf84b8d8e1ca0811ff05a5dc8b)
repository can be useful as an optional research and test reference. Its
author-created code is MIT, but its own README says files pulled from LEGO
firmware or filesystems remain licensed by LEGO. This project therefore does
not automatically fetch or vendor those files.

The production NuttX configuration exposes its console only over USB CDC.
Renode's F4 model does not provide a functional OTG FS device, so early tests
must use symbols, PC progress, and the fixed RAMLOG region. A diagnostic UART
build may aid debugging but cannot satisfy the unchanged-image gate.

The protected suite has two deliberately separate proofs. The unchanged image
must reach `stm32_bringup`. A second test then returns from that function at
the CPU hook boundary and requires `nsh_main`; this isolates and proves the
kernel-to-protected-userspace transition while the board peripherals are being
modeled. It is labeled as an isolated-boundary test and is not reported as an
unchanged full boot.

A new MIT-licensed model layer attaches an LSM6DS3TR-C register subset at
I2C2 address `0x6a`, a command-level W25Q256JV behind the real PB12 chip-select
path on SPI2, and a TLC5955 byte sink on SPI1. The no-function-hook model gate
proves that the unchanged firmware completes IMU and SPI2 flash initialization
and enters `tlc5955_initialize`. The private MIT Renode fork supplies the
request-paced SPI/UART DMA behavior needed for those transfers. This remains a
board-bring-up milestone, not yet an unchanged userspace boot proof.

The retained board-stub gate runs all of `stm32_bringup` while isolating the
same five synchronous initialization/update functions, then requires both
`nsh_main` and `btsensor_main`. It remains explicitly labeled as a stubbed
diagnostic and must not be presented as peripheral-fidelity simulation.

The rebuilt original `spike-nx` protected pair also passes its unchanged reset,
`nx_start`, `board_late_initialize`, and `stm32_bringup` milestones. Its staged
kernel is 221,180 bytes (SHA-256 `31852ec0ba70c6f66fa16ed56b14c3226598121b7f40cc607aa61b6fb1ef77b0`)
and its user image is 401,192 bytes (SHA-256
`fcabc6e45354092432f3db777dc86b0a96a1f2337701c685155ebce50ceed8c7`).
These locally built images remain ignored inputs.

The platform is deliberately incomplete. Clock fidelity, the remaining
synchronous board bring-up, LPF2 devices, and USB are tracked in `PLAN.md` C8. A
passing emulator run is never evidence for RF behavior, TI service-pack
semantics, electrical behavior, or physical timing.

## Virtual HCI boundary

`tools/test_renode_virtual_hci_bridge.sh` builds and tests a small Apache-2.0
TCP controller process around the same `virtual_hci`/H4 implementation used by
the native simulator. Renode's raw `ServerSocketTerminal` connects it directly
to `sysbus.usart2`. Vendor HCI commands have an explicit opt-in acknowledgement
policy: their payload is not parsed, interpreted, retained, or executed. This
allows an opaque, locally supplied TI bootstrap stream to cross the simulated
controller boundary without making the bridge an implementation of TI
firmware.

Set `BRICKWRIGHT_RENODE_FIRMWARE_TEST=1` to run the protected-image boundary
test after the standalone socket test. With the custom Renode fork it crosses
`physical_open`, streams the opaque service pack through the external lawful
responder, and reaches `physical_start_host`. The fork models RX/TX request
routing, request persistence across stream setup, circular NDTR reload, and
USART IDLE behavior. The gate now continues through `bt_enable()`,
`settings_load()`, hub-transport registration, and the daemon's ready-to-wait
boundary. A linker regression check ensures that the Zephyr net-buffer pool
table remains inside NuttX's protected initialized-data range.

## Local run

```sh
tools/install_renode.sh
# Stage lawfully obtained images under .local/firmware-images/.
tools/test_renode_opaque_images.sh
# After staging both NuttX builds with tools/stage_nuttx_image.py:
tools/test_renode_protected_images.sh
tools/test_renode_virtual_hci_bridge.sh
```

To exercise the custom fork, set `RENODE_DIR` for the test commands, for
example `RENODE_DIR=/path/to/renode-spike-prime`. The fork source and model
tests live in the public repositories `CrispStrobe/renode-spike-prime` and
`CrispStrobe/renode-infrastructure-spike-prime`. The HCI script selects
`spike-prime-custom-dma.repl`; the default `spike-prime.repl` deliberately
remains loadable by pinned stock Renode for the bounded public-model gates.

All local image staging remains below ignored `.local/` paths.
