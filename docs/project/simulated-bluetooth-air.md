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
(`BOARD_CONFIG=simulation-hci`) runs here; it sends no vendor commands and the
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

The following are recorded results from the earlier simulation-profile image
in Renode, with every station a separate node on one bw-air/1 hub. They are
not a qualification receipt for a later image. The default `simulation`
profile now leaves Bluetooth autostart disabled; build the explicit
`simulation-hci` profile and rerun the test for Bluetooth changes:

| path | status |
|---|---|
| Host bring-up against the air's controller (0 vendor, 0 unknown commands) | works |
| LE advertising, connect, FD02 discovery, InfoRequest write, InfoResponse notification | works |
| The same round trip through `scratch_link_node.py` (`/scratch/ble`), as lite would make it | works |
| A second central after the first LE link ends (advertising resumes in 0.1 s) | works |
| An emulated micro:bit (SoftDevice HLE) on the same air: a central sees both boards and discovers the micro:bit's UART service | works |
| Classic page, SDP (SPP record on RFCOMM channel 5), Secure Simple Pairing | works |
| Classic encryption | simulated: the air reports AES-CCM on to both hosts; no cipher runs |
| RFCOMM/SPP: open the channel, `PING` → `OK PONG` | works |

Open: the SPP record advertises RFCOMM channel 5, while the legacy SPIKE
Classic extension's Linux and macOS Scratch Link backends open channel 1
directly (`classic-protocol.md`). The SPP line protocol is btsensor's; the
legacy JSON RPC adapter (`btsensor_classic.c`) is reached only for lines it
recognises.

## Thread synchronization requirements

The compatibility layer uses a recursive pthread mutex for its IRQ-lock
interface, including nested intrusive-list operations. All firmware profiles
enable `CONFIG_PTHREAD_MUTEX_TYPES`; the NuttX build rejects its absence.
The regression compiles the actual pinned NuttX mutex-attribute implementation
and verifies that a disabled configuration returns `ENOSYS` instead of
creating the required recursive lock.

Virtual HCI producers and consumers share a condition variable with different
wait predicates, so queue changes wake all waiters. PSA cryptography also
enables Mbed TLS pthread locking for concurrent Bluetooth workers. Focused
host regressions exercise queue contention, list interleaving and concurrent
known-vector encryption. Actual protected-firmware HCI startup remains a
separate required qualification gate.
