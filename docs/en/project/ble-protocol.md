# SPIKE 3 BLE protocol inventory

This document inventories Brickwright's two modern-firmware extensions:
`spikeprimeble` (direct Web Bluetooth) and `legospikeprimeBLE` (Scratch Link
BLE). Both extension implementations are MPL-2.0 and are used only as
behavioural references. No source from either is included here.

The inspected files are blobs `d8c59c5c46e03729fe6fe871f1ce1052904c10cd`
and `75a22e91dc903e8cda1b832171c236161b3f126e` in Brickwright commit
`eaeee9bbab39a7b67727a2d3b466aed200b71282`.

The wire facts were cross-checked against the LEGO Group's public
[SPIKE Prime protocol documentation](https://github.com/LEGO/spike-prime-docs/tree/446549146df626f5d7f332b0ea3cd0205ce23711).
That documentation has a modified Apache licence. We use it as a protocol
reference, but do not copy its examples or documentation into the target.

## One peripheral, two host paths

Both extensions expect exactly the same GATT peripheral and binary message
family. They differ only in how the browser reaches it:

| Property | `spikeprimeble` | `legospikeprimeBLE` |
|---|---|---|
| Host API | Web Bluetooth directly | Scratch Link `/scratch/ble` JSON-RPC |
| Scan filter | advertised FD02 service | same filter passed to Scratch Link |
| Framing across notifications | assumes one notification is one frame | accumulates bytes through the `0x02` terminator |
| Write representation | `BufferSource` | base64 with explicit `encoding` |
| Nominal send limit | none | 20 calls/second; excess calls are dropped |
| Initial handshake | InfoRequest, then notification request after fixed waits | notification request only; no InfoRequest |

A single virtual GATT peripheral can serve both, provided the host-side virtual
backends reproduce their respective APIs. The Scratch Link BLE JSON-RPC layer
is not visible to firmware.

## Advertising and GATT

The hub advertises service UUID `0000fd02-0000-1000-8000-00805f9b34fb`.
Neither extension filters by local name, manufacturer data, address, RSSI, or
appearance.

| Attribute | UUID | Client operation |
|---|---|---|
| Primary service | `0000fd02-0000-1000-8000-00805f9b34fb` | discover |
| Hub RX | `0000fd02-0001-1000-8000-00805f9b34fb` | client writes framed messages |
| Hub TX | `0000fd02-0002-1000-8000-00805f9b34fb` | client enables notifications |

The published protocol requires write-without-response on RX. The direct
extension calls the legacy `writeValue()` API, which commonly selects a
response write, and the Scratch Link extension leaves `withResponse` unset.
Our GATT characteristic should expose write-without-response and may also
support write-with-response for compatibility. Host code must explicitly
prefer without-response.

No pairing, bonding, passkey, or security level is requested by either
extension. Those remain policy choices for our firmware and hardware tests.

## Binary framing

All multi-byte fields are little-endian. A logical message is framed as:

1. Apply the SPIKE three-delimiter COBS variant, escaping `0x00`, `0x01`, and
   `0x02` with a maximum block length of 84.
2. XOR every encoded byte with `0x03`.
3. Optionally prefix high-priority traffic with `0x01`.
4. Append `0x02` to terminate the frame.

The COBS code word is `block_size + 2 + delimiter * 84`, where block size
includes the code word. The two extensions look different (`CODE_OFFSET` 2
versus 3) because they count the block differently; for ordinary inputs their
minimum emitted code word is 3. C2.4 will settle equivalence using independently
written fixtures, including delimiter and 84-byte boundaries.

The stream parser must support fragmented, coalesced, and priority-interleaved
traffic. `0x01` pauses low-priority assembly for a high-priority frame; `0x02`
ends the active frame or begins low-priority assembly. The direct extension
does not implement this streaming/priority state machine and is therefore
non-conformant for fragmented or multiple frames. The virtual Web Bluetooth
backend must not hide this defect by inventing notification boundaries;
Brickwright should share the correct stream decoder with both extensions.

Frames carry no separate checksum. Integrity below this layer comes from BLE;
upload operations carry CRC fields where their message definitions require it.

## Handshake and standard messages

The standard connection sequence is: connect GATT, enable TX notifications,
send InfoRequest (`0x00`), parse InfoResponse (`0x01`), and honor the negotiated
maximum packet/message/chunk sizes. InfoResponse fields are RPC version,
firmware version, maximum packet size, maximum message size, maximum chunk
size, and product group/device type.

The direct extension reads maximum packet size at bytes 9-10 and maximum chunk
size at bytes 13-14, but does not read maximum message size and never uses
either negotiated value. It writes each complete frame in one operation. The
Scratch Link extension does not request or parse the size negotiation at all.
Both can exceed the GATT write limit for tunnel payloads. Correct host adapters
must segment a framed byte stream into writes no larger than negotiated packet
size; the firmware must reassemble framing across writes.

Message types observed or named by the extensions are:

| Type | Name | Extension behaviour |
|---:|---|---|
| `0x00` | InfoRequest | sent only by direct extension |
| `0x01` | InfoResponse | sizes partially parsed by direct extension; ignored by Scratch Link extension |
| `0x1e` | ProgramFlowRequest | named only |
| `0x1f` | ProgramFlowResponse | logged/ignored |
| `0x20` | ProgramFlowNotification | logged/ignored |
| `0x21` | ConsoleNotification | text appended only by Scratch Link extension |
| `0x28` | DeviceNotificationRequest | interval `100` ms in uint16 LE |
| `0x29` | DeviceNotificationResponse | acknowledged/logged, status not validated |
| `0x32` | TunnelMessage | uint16 LE payload length plus UTF-8 payload |
| `0x3c` | DeviceNotification | uint16 LE payload length plus device records |

Neither extension implements file upload, chunk transfer, slot clearing, hub
name, firmware update, or a program-start sequence.

## Device notification records

Both parsers expect a sequence of records in a DeviceNotification payload:

| Type | Length | Fields consumed |
|---:|---:|---|
| `0x00` battery | 2 | percentage |
| `0x01` IMU | 21 | face-up, yaw face, yaw/pitch/roll, acceleration and gyro as signed int16 |
| `0x02` 5x5 display | 26 | neither extension fully consumes it |
| `0x0a` motor | 12 | port, device type, absolute position, power, speed, relative position |
| `0x0b` force | 4 | port, value, pressed flag |
| `0x0c` color | 9 | port, signed color ID, RGB uint16 values |
| `0x0d` distance | 4 | port and signed millimetres (`-1` means no object) |
| `0x0e` 3x3 matrix | 11 | port and nine packed color/brightness pixels |

The direct extension advances motor records by 11 instead of 12 and reads the
relative motor position from the wrong offset. It also treats distance as
signed correctly but ignores most IMU fields. The Scratch Link extension uses
12 bytes for motors, but decodes distance as unsigned and only fills
yaw/pitch/roll. Both stop parsing on an unknown device type; neither validates
all record bounds or the complete declared payload length. These are extension
defects. Our codec must use the published lengths and signedness and reject a
malformed entire notification atomically.

## Tunnel payloads and extension operations

The authoritative source is
[`CrispStrobe/extensions@fc94e19`, `extensions/CrispStrobe/legospike_ble.js`](https://github.com/CrispStrobe/extensions/blob/fc94e19ee259c9fc8465c5a0b69dc366085ab376/extensions/CrispStrobe/legospike_ble.js#L751-L808).
Its exact UTF-8 JSON payloads are:

- line 758: `{"m":"motor","p":{"port":0,"speed":75}}` (values vary);
- line 775: `{"m":"motor","p":{"port":0,"speed":0,"end_state":1}}`;
- line 807: `{"m":"display_3x3","p":{"port":2,"data":[0,0,0,0,153,0,0,0,0]}}`.

The direct extension does not send `matrix_pixel` or `sensor` tunnel methods.
Its sensor reporters consume DeviceNotification state (lines 811 onward).

It assumes that a hub-side program already understands those application JSON
objects. It does not upload or start such a program, wait for readiness, parse
tunnel replies, correlate requests, or report application errors.

`legospikeprimeBLE` instead sends current-firmware Python source as a
TunnelMessage for motors, paired movement, 5x5 display, sound, yaw, and exposed
Python blocks. A standard TunnelMessage delivers opaque bytes to a running
program's module-tunnel callback; the message type alone neither requires nor
forbids Python execution. The extension does not upload or start that receiver,
but the existing path has been reported working with LEGO firmware and must be
preserved until a hardware trace identifies the receiver and reply contract.
It was incorrect to infer non-execution merely from the published envelope.

Our firmware can implement a deterministic tunnel service for the neutral hub
operations from C2.3, allowing the direct extension's small JSON subset to be
adapted. The simulator may implement a bounded compatibility translator for
the observed Python tunnel subset, but must not expose arbitrary filesystem or
system access. A future compatibility helper may upload a separately licensed,
bounded hub program using the documented file/program-flow protocol.

## Errors, disconnect, and reconnect

Both extensions clear cached state after GATT disconnect and require the user
to scan/connect again; neither automatically reconnects or restores streaming.
The direct extension catches connection errors and has no command-response
tracking. The Scratch Link wrapper applies a five-second timeout to its own
JSON-RPC calls, but dropped rate-limited writes resolve successfully and no
hub-level acknowledgement is awaited.

Required clean behaviour is: bounded frame/message buffers, explicit malformed
frame rejection, negotiated write segmentation, operation IDs and status
responses at the application layer, bounded timeouts, rejection of outstanding
operations on disconnect, and independent motor failsafe on link loss.

## Acceptance decisions

| Area | C2.2 disposition |
|---|---|
| FD02 advertising, RX writes, TX notifications | implement |
| SPIKE COBS/XOR/priority framing | implement from independent fixtures |
| Info handshake and negotiated limits | implement fully |
| Device notifications | implement using published record layouts |
| Tunnel transport | implement as opaque bounded messages |
| Extension JSON tunnel vocabulary | adapt into C2.3 neutral operations |
| Observed tunnelled-Python subset | preserve and verify on hardware; simulate through a bounded translator |
| Program/file upload | defer until required for a bounded compatibility helper |
| Extension parser/write bugs | fix in Brickwright; do not emulate in firmware |
| Reconnect | explicit rescan matches current extensions; safe state is mandatory |

The protocol can be simulated without TI software or CC2564C emulation: expose
the virtual GATT attributes and run the same framing and message codecs against
`HubState`. Physical tests remain necessary for advertising, ATT MTU/write
behaviour, controller flow control, connection loss, and coexistence.
