# TI BTS loader

The MIT-licensed loader streams a caller-supplied BTS container without changing
its bytes. The actual service pack in `third_party/ti-cc2564c/` remains governed
only by its adjacent TI licence, is restricted to TI devices, and is not project
source.

The loader recognizes the public container header and action boundaries,
forwards complete H4 commands, and accepts standard HCI Command Complete or
Command Status events. It does not interpret vendor opcodes or parameters.
Unknown or recursive actions fail closed; required delay or serial callbacks
must be present.

The controller lifecycle opens `/dev/ttyBT`, resets the controller, streams the
verified service pack, applies declared serial transitions, starts the Zephyr
host, and owns cleanup. eHCILL is implemented at the host transport seam; TI
bytes are never patched.

Tests use synthetic records containing no TI firmware bytes. Hash and licence
requirements are defined in `docs/en/project/ti-service-pack.md`.
