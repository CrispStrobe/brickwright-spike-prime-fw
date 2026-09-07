# Legacy SPIKE Classic protocol inventory

This document freezes the behaviour expected by Brickwright's
`spikeprimeBTC` extension. It is an interoperability record, not a copy of the
extension. The extension is MPL-2.0 and none of its implementation is reused
in this MIT/Apache source tree.

The reference inspected was the vendored extension blob
`a3c79bbf215abfedf38a95ab436f28495829def9` in Brickwright commit
`eaeee9bbab39a7b67727a2d3b466aed200b71282`. The behavioural observations below
must be confirmed on a legacy-firmware hub before hardware compatibility is
claimed.

## Layer boundaries

There are three distinct protocols:

1. The browser talks JSON-RPC 2.0 over the Scratch Link `/scratch/bt`
   WebSocket.
2. Scratch Link opens an unframed Bluetooth Classic RFCOMM byte stream.
3. The extension sends CR/CRLF-delimited JSON RPC and MicroPython source over
   that stream.

Brickwright simulation ends at layers 1 and 3. It does not emulate the
CC2564C, HCI, baseband, TI service pack, SDP state machine, or RF timing.

## Discovery, pairing, and SPP

The extension issues `discover` with Bluetooth Class-of-Device major `8`
(Toy) and minor `1` (Robot), waits 15 seconds, and presents each
`didDiscoverPeripheral` or `userDidPickPeripheral` result. It supplies no name
or OUI filter and sends no PIN.

`connect` contains only the selected `peripheralId`. Pairing is therefore an
operating-system/Scratch-Link prerequisite. Brickwright's Windows and Android
backends enumerate paired or bonded SPP devices; this is host behaviour, not a
promise made by the extension.

The historical macOS Scratch Link backend opens RFCOMM server channel 1
directly. Current Brickwright Linux and macOS backends do the same. Android
uses the standard Serial Port Profile UUID
`00001101-0000-1000-8000-00805f9b34fb`; Windows enumerates SPP services and
connects to the selected service endpoint. The extension itself neither runs
SDP nor selects a channel. Channel 1 and the advertised SPP record remain
hardware-verification requirements for our firmware.

Only one peripheral/session is supported at a time. The RFCOMM payload is an
arbitrary byte stream: reads may be fragmented or coalesced, and writes may be
split at the negotiated RFCOMM MTU without changing their meaning.

## Scratch Link JSON-RPC contract

All envelopes use `jsonrpc: "2.0"`. Client request identifiers increase from
zero independently of hub-level request identifiers.

| Direction | Method | Parameters/result |
|---|---|---|
| client to link | `discover` | `{majorDeviceClass: 8, minorDeviceClass: 1}` |
| link to client | `didDiscoverPeripheral` | `peripheralId`, `name`, and `rssi` |
| link to client | `userDidPickPeripheral` | same peripheral fields |
| link to client | `userDidNotPickPeripheral` | no required fields |
| client to link | `connect` | `{peripheralId}`; optional `pin` is supported by the wrapper but unused |
| client to link | `send` | byte buffer encoded by Scratch Link's buffer convention |
| link to client | `didReceiveMessage` | `{message: BASE64, encoding: "base64"}` |
| link to client | `ping` | extension wrapper returns `42` |

Successful calls return a JSON-RPC result; transport failures return an error.
The reference backends commonly use application code `-32000`, while the old
macOS implementation also uses `-32500`. Consumers must treat any JSON-RPC
`error` as failure rather than keying behaviour to either code.

### Confirmed extension/backend mismatch

Received bytes are correctly expected as base64. Sent data, however, is passed
as a plain JavaScript string in `{message: text}` with no `encoding`. Scratch
Link's buffer contract and all Brickwright native backends interpret the
default as base64. Ordinary command text is not generally valid base64, so the
checked-in extension cannot reliably transmit through those backends as
written.

This is a blocker, not part of the firmware protocol. Brickwright must fix the
extension to send UTF-8 bytes as base64 (and specify `encoding: "base64"`) or
add an explicitly named UTF-8 mode end-to-end. Silent heuristic decoding is
rejected because valid-looking base64 text would be ambiguous.

## Hub stream framing

The extension emits two forms:

- compact JSON followed by a single carriage return (`0d`);
- MicroPython source followed by CRLF (`0d 0a`), plus a standalone Ctrl-C
  (`03`) immediately after connection.

It receives arbitrary chunks, UTF-8 decodes each chunk, appends an incomplete
tail, and recognizes complete records only at CRLF. Empty/whitespace-only
records are discarded. A complete record is parsed as JSON first; on JSON
failure it is treated as textual console/sensor output.

This decoder is not fully streaming-safe: a UTF-8 sequence split across two
RFCOMM notifications can be replaced because the `TextDecoder` is not used in
streaming mode. Our output is therefore restricted to ASCII until the
extension is repaired. There is no maximum receive-record size.

## Hub JSON messages

Requests are compact objects with `m` (method), `p` (parameters), and optional
four-character `i` (request ID). A response containing the same `i` resolves
the pending operation; response content and errors are otherwise ignored.
Unsolicited messages use numeric `m` values:

| `m` | Meaning consumed by extension |
|---:|---|
| `0` | Current state: six port entries in `p[0..5]`; optional yaw/pitch/roll in `p[8]` |
| `2` | Battery percentage in `p[1]` |
| `3` | Button name and 0/1 state in `p[0..1]` |
| `4` | Orientation or gesture name in `p` |

Current-state device IDs recognized are 48/49 motor, 61 color, 62 distance,
and 63 force. Unknown devices become `unknown`. The command names emitted by
blocks are:

- `trigger_current_state`
- `scratch.motor_run_for_degrees`
- `scratch.motor_run_timed`
- `scratch.motor_start`
- `scratch.motor_stop`
- `scratch.display_text`
- `scratch.display_image`
- `scratch.display_clear`
- `scratch.display_set_pixel`
- `scratch.center_button_lights`
- `scratch.sound_beep`

The finite Classic adapter implements the exact compact JSON emitted for
`motor_start`, `motor_stop`, `motor_run_timed`, `display_clear`, and
`display_set_pixel`. The display coordinates are zero-based values 0 through
4. The extension's 0-through-9 display brightness is scaled to the existing
0-through-100 5x5 matrix backend. `display_image` remains unsupported because
the current RGB LED interface exposes only individual channel updates and
cannot commit all 25 pixels atomically.

Timed runs are limited to
60 seconds, hold and stall detection are rejected, and the request ID is
resolved only after the selected coast/brake end action. One transport-neutral
deadline queue covers all six physical ports; disconnect cancels it and the
port backend supplies the motor failsafe. Each completion carries the
exclusive ownership token returned by its start command, so a later BLE or
Classic command can take over the port without being stopped by an old timer.
`motor_run_for_degrees` remains
explicitly unsupported until the port backend can prove encoder-target
completion instead of estimating it in software.

Motor, display, light, and sound blocks often fall back to MicroPython if a
JSON request rejects. Because the response parser never interprets a hub-level
error field, that fallback only works when the Scratch-Link `send` request
fails, not when the hub reports an application error.

## Text records and MicroPython dependency

After connection the extension sends Ctrl-C, waits 250 ms, imports `hub`,
prints `PYTHON_AVAILABLE`, and requests current state. Seeing that marker makes
it upload and invoke an infinite 100 ms sensor loop. The following ASCII
records are consumed:

| Prefix | Payload |
|---|---|
| `PYTHON_AVAILABLE` | enables the uploaded monitoring loop |
| `SENSORS:` | angles, acceleration, orientation, temperatures, motor values, and optional power, separated by commas and pipes |
| `GESTURE:` | `TAPPED`, `DOUBLETAPPED`, `SHAKE`, or `FREEFALL` |
| `>>>` | appended to a bounded REPL-output string |

Many blocks transmit arbitrary old-firmware MicroPython using the `hub` API:
movement/motors, matrix and center LED, sounds, sensor lights, yaw, files, and
an exposed REPL. Exact unmodified-extension compatibility therefore requires a
compatible Python console and API, not merely JSON commands.

Our initial firmware target is the safer documented JSON subset plus state
events. Arbitrary Python, filesystem access, and the uploaded infinite loop
are explicitly deferred. Brickwright should revise the extension to use the
neutral hub operations defined in C2.3; a later compatibility mode can add a
bounded command translator without embedding MicroPython.

## Errors, timeouts, and reconnect

Discovery times out in the UI after 15 seconds, although discovery
notifications can cancel that timer. There is no connect timeout, hub-response
timeout, pending-request limit, or rejection of pending hub requests on
disconnect. Unknown/late response IDs are ignored.

Closing the WebSocket or failing `send` while marked connected resets cached
hub state and reports connection loss. A user disconnect closes the socket and
also resets state. There is no automatic reconnect: scanning creates a new
Scratch Link socket and a new discovery cycle. The firmware must stop motors
safely on link loss independently of this client behaviour.

## Acceptance decisions

| Area | C2.1 disposition |
|---|---|
| Class-of-Device discovery and one selected peripheral | implement |
| SPP UUID / RFCOMM byte stream | implement; verify channel and SDP record on hardware |
| CR/CRLF JSON and ASCII record framing | implement with bounded streaming parser |
| Eleven named JSON operations and four state-event types | carry into neutral contract |
| Base64-less outbound Scratch Link messages | reject as extension defect |
| Arbitrary MicroPython and file/REPL access | defer; revise extension to neutral operations |
| Silent fallback based on hub application errors | reject; define explicit result/error replies |
| Unbounded pending requests and no response timeouts | reject; specify limits in C2.4 |
| Automatic reconnect | not present; simulator must reproduce explicit rescan semantics |

This inventory describes observed software behaviour. Bluetooth pairing mode,
the actual legacy hub Class-of-Device, its SDP record/channel, command reply
shape, and disconnect safety still require packet captures or black-box tests
on hardware; no claim about those facts is inferred from TI controller code.
