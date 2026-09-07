# Brickwright SPIKE Prime firmware

This project develops a permissively licensed NuttX firmware and an
instruction-level SPIKE Prime simulation.

!!! danger "Simulation only"
    Do not install or flash this firmware on a physical hub. Renode results do
    not prove electrical, motor, battery, thermal, radio, update, or recovery
    safety. The repository `SAFETY.md` defines the release gate.

## Start here

- [Hub architecture](drivers/architecture.md)
- [Driver readiness](drivers/implementation-plan.md)
- [Bluetooth architecture](drivers/bluetooth.md)
- [Classic protocol](project/classic-protocol.md)
- [BLE protocol](project/ble-protocol.md)
- [Neutral hub contract](project/hub-contract.md)
- [Licence and provenance](project/provenance.md)

Build with `make`. Run the simulator gates from the repository root:

```bash
tools/install_renode.sh
tools/test_renode_protected_images.sh
tools/test_renode_virtual_hci_bridge.sh
```

Opaque LEGO and Pybricks images are optional user-supplied local inputs. The
repository neither fetches nor publishes them.
