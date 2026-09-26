# Simulated Bluetooth air

The emulated SPIKE Prime hub joins the project's one simulated Bluetooth air,
**bw-air/1**. The air, its contract and its tools live in one place:
[renode-spike-prime `tools/bw-air/`](https://github.com/CrispStrobe/renode-spike-prime/tree/feat/nrf-softdevice-hle/tools/bw-air)
(`AIR.md`, `airhub.py`, `bumble_air.py`, `hci_node.py`,
`scratch_link_node.py`). This repository does not carry its own air. The same
air carries emulated micro:bit / Calliope boards (a clean-room SoftDevice API
emulation in Renode or labwired), bumble peers, and Scratch Link clients such
as Brickwright lite, so a SPIKE hub and a micro:bit see each other.

## How the hub joins

Renode exports USART2, the CC2564C HCI UART, as a TCP socket
(`emulation CreateServerSocketTerminal`, `connector Connect sysbus.usart2`).
`hci_node.py --renode-hci spike=127.0.0.1:PORT@02:B1:0E:5A:17:01` puts a
bumble controller on that byte stream and on the air. The firmware's own
Zephyr host then advertises, accepts LE and BR/EDR connections, and serves the
FD02 GATT service and SPP. Only the TI-free simulation profile
(`BOARD_CONFIG=simulation`) runs here; it sends no vendor commands and the
controller refuses any that arrive. The profile also enables
`CONFIG_APP_BTSENSOR_START_VISIBLE`, the equivalent of `btsensor bt on`,
because Renode has no USB console.

## End-to-end test

`simulation/bluetooth-air/test_spike_air.py` starts the hub, Renode with the
simulation image, and the hub's HCI node, then drives peers on the air:

```sh
python3 simulation/bluetooth-air/test_spike_air.py \
  --renode /path/to/renode-spike-prime \
  --images .local/firmware-images/brickwright-simulation \
  [--microbit] [--scratch-link 20131] [--classic --skip-le]
```

- default: a central finds the hub, connects, discovers FD02, writes an
  InfoRequest and decodes the InfoResponse notification;
- `--scratch-link PORT`: the same round trip through the Scratch Link node, as
  lite would make it;
- `--microbit`: an emulated micro:bit (`tools/nrf-softdevice-hle/fake_app.py`,
  the SoftDevice HLE library) joins the same air; the central must see both
  advertisers and find the micro:bit's UART service;
- `--classic`: page, SDP, pairing, encryption and RFCOMM to the hub's SPP.

`--air-tools` (or `$BW_AIR_TOOLS`) names `tools/bw-air`; by default it is taken
from `--renode`.

The simulated air proves protocol behaviour only. It says nothing about RF,
timing, coexistence, or qualification, and it never involves TI or Nordic
controller firmware.

## Current reach with the SPIKE firmware

Measured with the unchanged simulation-profile image in Renode:

| path | status |
|---|---|
| Firmware host bring-up against the air's controller (31 standard HCI commands, 0 vendor, 0 unknown) | works |
| LE advertising seen by a central on the air | works (about 5 s after boot) |
| LE connect, GATT discovery of FD02, subscribe, InfoRequest write, InfoResponse notification | works |
| The same round trip through the Scratch Link gateway (`/scratch/ble`) | works |
| After the first LE link ends | does not work yet: the firmware stops processing HCI events once the disconnection is handled (no further receive work runs), so it neither re-advertises nor answers later requests; root cause open |
| Classic page and connect, SDP (SPP record on RFCOMM channel 5) | works |
| Classic Secure Simple Pairing (link key on both sides) | works |
| Classic encryption | simulated: the air reports AES-CCM on to both hosts; no cipher runs |
| RFCOMM/SPP channel open | does not work yet: after the encryption change the firmware does not answer the L2CAP connection request for RFCOMM |
