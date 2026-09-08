# Brickwright SPIKE Prime firmware

> **Simulation-only work in progress:** do not install or flash firmware from
> this repository on a physical LEGO hub. Read [SAFETY.md](SAFETY.md).

This repository develops a permissively licensed NuttX firmware for LEGO SPIKE
Prime and validates real ARM images in Renode. It uses a transport-neutral hub
API, an Apache-2.0 Zephyr Bluetooth host selection, and an opaque TI CC2564C
controller boundary.

## Current capability

The protected Brickwright image builds and executes in the custom Renode model
through board initialization, flash and IMU setup, byte-preserving TI payload
streaming, Bluetooth host enable, settings load, transport registration, and
daemon readiness. Native tests exercise Classic RFCOMM/SPP, BLE ATT/GATT, basic
SMP, shared protocol fixtures, and bounded peripheral commands.

Local manifests can run user-supplied official LEGO v2/v3 and Pybricks images,
the original spike-nx build, and this firmware from their vector tables. Those
images are not fetched, committed, cached, or uploaded.

This is not full brick emulation. LPF2/motor dynamics, complete Bluetooth peers,
remaining device timing, interactive multi-image scenarios, fault recovery, and
soak gates remain in [PLAN.md](PLAN.md).

## Build and simulate

```bash
make
tools/install_renode.sh
tools/test_renode_protected_images.sh
tools/test_renode_virtual_hci_bridge.sh
```

Optional opaque-image tests consume ignored files under
`.local/firmware-images/`:

```bash
tools/test_renode_opaque_images.sh
```

See [simulation/renode/README.md](simulation/renode/README.md). A passing run
proves only its named software milestone.

## Repository map

- `apps/btsensor/`: transport-neutral Classic/BLE daemon and hub adapters
- `bluetooth/`: H4, lifecycle, eHCILL, and opaque BTS loader
- `protocol/`: hub schema, codecs, and fixtures
- `simulation/renode/`: platforms, manifests, and scenarios
- `third_party/zephyr-host/`: pinned Apache-2.0 Bluetooth host
- `third_party/ti-cc2564c/`: exact TI exception and adjacent licence
- `docs/en/`: contracts, hardware notes, and operator guidance
- `PLAN.md`: ordered unfinished work; `HISTORY.md`: accepted milestones

For Renode, `make nuttx BOARD_CONFIG=renode` builds a simulation-only image
with the permissive in-process Bluetooth controller. It neither requires TI
bytes nor operates the physical radio. See
[the Renode controller profile](docs/en/testing/renode-controller.md).

## Policy and documentation

Project source is MIT, Apache-2.0, BSD-3-Clause, or an approved comparable
permissive licence. The exact TI service pack is separately licensed and limited
to TI devices. No BTstack or official LEGO/Pybricks image is included. See
[LICENSE](LICENSE), [NOTICE](NOTICE), [THIRD_PARTY.md](THIRD_PARTY.md), and
[provenance](docs/en/project/provenance.md).

```bash
mkdocs build --strict
```
