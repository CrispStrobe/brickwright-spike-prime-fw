# Simulated Bluetooth air

The emulated SPIKE Prime hub joins the project's one simulated Bluetooth air,
**bw-air/1**. The air, its contract and its tools live in one place:
[renode-spike-prime `tools/bw-air/`](https://github.com/CrispStrobe/renode-spike-prime/tree/e0166acb028b162e972458f31d76cdb7dcdc518d/tools/bw-air)
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
  --existing-filesystem .local/firmware-images/existing-filesystem \
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

The earlier record used RFCOMM channel 5. The current qualified simulation
pair reports channel 1 through SDP, matching the legacy extension's direct
channel selection. The SPP line protocol is btsensor's; the legacy JSON RPC
adapter is reached only for lines it recognises. The peer PING/PONG test does
not by itself qualify every legacy extension operation.

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


## Current peer qualification — 2026-10-03

The helper now runs actual display functions through the SPI1/PA15 model;
no display function returns are substituted. It verifies protected-image
manifest hashes and vectors, requires HCI Reset, zero vendor/unsupported
commands, and daemon readiness before reporting success. Direct LE tests
validate the complete 17-byte InfoResponse, disconnect, then require a second
central to rediscover and complete the same request. Scratch Link uses bounded
per-frame decoding for fragmented/coalesced notifications and checks the same
response fields. Classic tests discover SPP through SDP, authenticate, receive
the controller's modeled encryption status, and exchange `PING` / `OK PONG`.
No cipher or RF behavior is qualified by that controller status.

The selected public runtime is `e0166acb028b162e972458f31d76cdb7dcdc518d`.
The host environment pins Bumble 0.0.235, websockets 15.0.1 and their dependencies
in `tools/bluetooth-air-requirements.txt`. `policy/bluetooth-air-host-inputs.json`
records air source hashes, package versions and installed-notice hashes; the peer wrapper
checks them before execution. These are host-only dependencies; see
[the third-party notice](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/THIRD_PARTY.md#host-only-simulated-bluetooth-air).

Use Python 3.11 or later. The wrapper runs on Linux with `unshare`, `ip` and
`runuser`; a non-root caller needs noninteractive sudo for namespace creation.
After building/staging `simulation-hci`, installing
the pinned source-built runtime and generating the explicit filesystem fixture,
`tools/test_bluetooth_air.sh` runs three separate fresh machines: direct LE
with reconnect, Scratch Link, and Classic. The HCI CI profile selects this gate.
Results, traces and package versions remain under ignored `.local` storage;
CI publishes no firmware or test artifacts. The wrapper creates an ephemeral
network namespace for each peer run, enables only its loopback interface, and
runs the test as the original caller. Renode's HCI terminal otherwise binds all
interfaces; a standalone Python invocation keeps that underlying behavior.
Before isolation, a bounded paused platform load prepares Renode's per-user
SVD cache; it loads no firmware and creates no terminal. Namespace setup changes
no host interface, route or firewall rule.

`--existing-filesystem` is an explicit fixture choice, validated and programmed
through the existing NOR SPI loader before guest execution. Omitting it retains
initially erased flash; the wrapper's peer tests do not qualify first-format
behavior, which remains a separate exhaustive boot gate. Invalid image/fixture
hashes fail before subprocesses start. The harness bounds waits, records
failures, disconnects peers and reaps its owned process groups, including
background descendants of an exited shell. Synthetic framing and actual-helper
lifecycle regressions cover fragmentation, coalescing, malformed responses,
bounds, cancellation, tool selection and process ownership.

The first local runs passed direct LE/reconnect, Scratch Link and Classic with
zero vendor/unsupported commands and no cleanup errors. The later exact wrapper
and full public matrix require their own receipts. Browser/legacy-operation,
micro:bit coexistence, persisted bonds, RF/security and physical hub behavior
remain separate from these three peer paths.
