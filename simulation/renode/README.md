# SPIKE firmware simulation

This directory executes real STM32 images. It complements Brickwright’s
transport-level virtual hub; it does not prove physical hardware behavior.

## Targets

| Target | Input | Current gate |
| --- | --- | --- |
| `lego-v2` | local official legacy image | vectors and bounded progress |
| `lego-v3` | local official modern image | vectors and bounded progress |
| `spike-nx` | local protected build | symbol boot milestones |
| `pybricks` | local release image | vectors and bounded progress |
| `brickwright` | local protected build | daemon readiness through H4 bridge |

Opaque images remain under ignored `.local/firmware-images/`, are verified by
target manifests, and are never fetched or uploaded. The optional public
`gpdaniels/spike-prime` snapshot may be used as a research source, subject to
the licences stated there.

## Model boundary

The SPIKE Prime platform defines STM32F413 memory, 320 KiB SRAM, 32 MiB external
flash, and board wiring. MIT models cover a TLC5955 register/latch surface, an
LSM6DS3TR-C subset, W25Q256 commands, and required DMA/SPI/UART behavior.

The H4 bridge acknowledges selected opaque vendor commands without parsing,
retaining, or executing their parameters. It also provides standard controller
events used by the permissive host tests. This does not emulate TI firmware,
radio behavior, or Bluetooth qualification.

`spike-prime.repl` remains compatible with pinned stock Renode.
`spike-prime-custom-dma.repl` adds request wiring supplied by the public custom
fork. A diagnostic function hook must be named as such and cannot satisfy an
unchanged-image milestone.

## Run

```bash
tools/install_renode.sh
tools/test_renode_protected_images.sh
tools/test_renode_virtual_hci_bridge.sh
tools/test_renode_opaque_images.sh  # optional local inputs
```

Set `RENODE_DIR=/path/to/renode-spike-prime` to use the custom fork. Set
`BRICKWRIGHT_RENODE_FIRMWARE_TEST=1` for the protected-image H4 scenario.

Missing peripherals and exact acceptance gates are maintained in `PLAN.md`.
Passing simulation is never permission to flash a hub.
