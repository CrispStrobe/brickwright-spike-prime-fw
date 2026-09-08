# Renode Bluetooth controller profile

Build the simulator-only firmware with:

```sh
make nuttx BOARD_CONFIG=renode
```

`CONFIG_APP_BTSENSOR_VIRTUAL_CONTROLLER=y` selects the Apache-2.0 in-process
HCI model. The model supports the command, ACL, BLE, and Classic seams used by
the Brickwright daemon. It does not power the CC2564C, open `/dev/ttyBT`, load a
TI service pack, or provide a radio interface. Consequently, this profile is
for simulation only and must not be flashed to a hub.

The profile also disables the STM32 independent-watchdog automonitor. Renode
does not model the physical watchdog closely enough for it to be a valid
firmware safety test, and enabling it resets the simulated CPU during bring-up.
The hardware profile retains its watchdog configuration.

Board bring-up likewise does not arm the HPWORK starvation softdog in this
profile. Simulation scheduling and peripheral-model latency are not equivalent
to real-time hardware deadlines and can otherwise produce a false `PANIC()`.
`CONFIG_SCHED_HPWORK` remains enabled because the firmware services use the
queue; only the physical safety monitor is omitted. Hardware builds still arm
the monitor.

The normal `usbnsh` profile leaves this option disabled. Its CC2564C power,
UART, reset, and separately supplied service-pack path are unchanged.

The two profiles are fail-separated at build time:

- `renode`: no TI payload input or generated payload header is required;
- `usbnsh`: the allowlisted, separately licensed TI input remains mandatory.

Controller selection is compile-time only. Firmware filenames, environment
variables, and simulator behavior cannot silently select the virtual backend.

Renode may use the global `brickwright_simulation_daemon_ready` symbol as its
daemon-ready milestone. Execution reaches it only after services and the HCI
host start successfully. Hardware builds do not contain this symbol.
