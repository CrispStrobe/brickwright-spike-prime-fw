# Simulated Bluetooth air

The simulated air lets emulated hubs, emulated boards, and host software reach
each other over Bluetooth with no radio hardware and no vendor controller
firmware. It is one process, `simulation/bluetooth-air/bw_air_server.py`,
built on [bumble](https://github.com/google/bumble) (Apache-2.0).

## Model

The air is a single bumble `LocalLink`. Every station attaches a bumble
`Controller` to it. Advertising PDUs, LE connections (LL control PDUs and ACL),
and Classic connections (LMP and ACL) travel between controllers through the
link, so every station on one air can see and connect to every other. There is
one air per test or session; two airs never share traffic.

Controllers answer every HCI command. Unknown commands get Command Complete
with `UNKNOWN_HCI_COMMAND`. A short list of configuration writes with no effect
on the simulated link (page timeout, inquiry mode, link policy, and similar)
succeed so an unmodified host stack completes bring-up. Vendor commands
(OGF 0x3F) are always refused and counted: nothing on the air executes vendor
firmware.

## Attachment points

A station joins the air at one of three levels. Pick the lowest one the
emulated device already has.

| level | interface | who uses it |
|---|---|---|
| UART | Air dials a TCP socket that carries the device's HCI UART (H4). One controller per socket. `--renode-hci NAME=HOST:PORT@BDADDR` | Renode machines whose firmware contains a Bluetooth host: the SPIKE Prime hub exports USART2 with `emulation CreateServerSocketTerminal`. |
| HCI | Air listens on a TCP port; each connection is an HCI host speaking H4 and gets its own controller and address. `--hci-listen PORT` | Emulators that have or build an HCI host: a micro:bit SoftDevice emulation that translates `sd_ble_*` calls into HCI, BlueZ through `btproxy`, a second Renode machine, test harnesses. |
| Peer | In-process bumble `Device` (host plus controller) created with `Air.add_peer`. | Scripted tests, and the Scratch Link gateway that serves browsers. |

Addresses: the air assigns public addresses. The UART level takes the address
on the command line; the HCI level derives `02:B1:0E:PP:PP:NN` from the port
and the connection number. A dial-in host may set a random static address for
LE as usual.

### Contract for a micro:bit (or any other) emulator

To share an air with the SPIKE hub, an emulator connects to the air's HCI port
and behaves as a Bluetooth host:

1. Open TCP to `127.0.0.1:PORT`; bytes are H4 (`0x01` command, `0x02` ACL,
   `0x04` event).
2. Send `HCI_Reset`, read the controller's features and buffer sizes, and set
   the event masks as any host does.
3. To be found, send the LE advertising parameter, data, and enable commands.
   To find others, scan. Connections, ATT, and L2CAP are ordinary HCI and ACL.

A SoftDevice emulation that implements the `sd_ble_*` API above a real host
stack (bumble's, run inside the emulator's process, or Zephyr's) meets this
contract directly. `test_air_selfcheck.py` is a working example: two bumble
hosts dial in, advertise a Nordic UART service, and a third station finds both,
connects to one, writes, and receives a notification.

## Scratch Link gateway for Brickwright lite

Brickwright lite reaches hardware through Scratch Link: JSON-RPC 2.0 over
WebSocket at `ws://127.0.0.1:20111/scratch/ble` and `/scratch/bt`. Its JS
virtual hub (`spike-prime-peripheral.js`, `spike-classic-scratch-link.js`)
replaces that socket with an in-page simulation.

`scratch_link_gateway.py` (prototype, `--scratch-link 20111`) serves the same
protocol, but each browser session becomes a bumble central on the air:

- BLE: `discover` scans the air and reports `didDiscoverPeripheral`;
  `connect` opens an LE connection and discovers GATT; `write`, `read`,
  `startNotifications`, and `stopNotifications` map to ATT, and notifications
  return as `characteristicDidChange`.
- BT: `discover` lists the air's Classic stations (bumble's link has no
  inquiry procedure); `connect` opens BR/EDR, finds the SPP record over SDP,
  and opens RFCOMM; `send` and `didReceiveMessage` carry the byte stream.

Lite's Classic extension opens `ws://127.0.0.1:20111/scratch/bt`; that is the
URL its virtual socket intercepts (`isClassicScratchLink`). With the virtual
hub not selected, the same socket reaches the gateway, so the Classic path to
the Renode hub needs no change in lite. The Web Bluetooth path used by the modern SPIKE extension would
need a small shim that forwards `navigator.bluetooth` GATT calls to the
gateway's BLE session; that shim belongs in lite and is not part of this
repository.

The gateway binds to loopback only. Run it instead of a real Scratch Link, not
beside one: both use port 20111.

## Running

```sh
python3 -m venv .local/tools/bumble-venv
.local/tools/bumble-venv/bin/pip install bumble
# End to end against the Renode-emulated SPIKE firmware (simulation profile):
.local/tools/bumble-venv/bin/python simulation/bluetooth-air/test_spike_air.py \
  --renode /path/to/renode-spike-prime \
  --images .local/firmware-images/brickwright-simulation
# The air alone, with dial-in HCI hosts:
.local/tools/bumble-venv/bin/python simulation/bluetooth-air/test_air_selfcheck.py
```

The simulated air proves protocol behavior only. It says nothing about RF,
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
