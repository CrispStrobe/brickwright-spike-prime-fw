# Bluetooth architecture

The active implementation uses the Apache-2.0 Zephyr host selection documented
in [the host audit](../project/zephyr-host-audit.md). BTstack is not part of the
source or build graph.

## Layers

1. `stm32_btuart.c` owns CC2564C power, clock, USART2, flow control, DMA, and
   interrupt-safe byte transfer.
2. The H4/eHCILL adapter handles sleep/wake control and transports HCI packets.
3. The controller lifecycle resets the radio, streams the exact opaque TI BTS,
   changes baud only where directed by public action framing, starts the Zephyr
   host, and unwinds failures in reverse order.
4. The Zephyr host provides HCI, GAP, L2CAP, SDP/RFCOMM, ATT/GATT, and SMP.
5. `btsensor` presents Classic and BLE services through the neutral hub API.

The TI payload is immutable and separately licensed. Host code may identify BTS
action boundaries and standard HCI completion/status events, but must not parse
vendor parameters, execute controller firmware, or alter bytes. See
[the TI boundary](../project/ti-service-pack.md).

## Physical interface

| Signal | MCU resource |
| --- | --- |
| HCI UART TX/RX | USART2 PD5/PD6 |
| RTS/CTS | PD4/PD3 |
| TX/RX DMA | DMA1 streams 6/7 |
| controller shutdown | PA2 |
| 32.768-kHz slow clock | TIM8 channel 4, PC9 |

The board-local lower half is authoritative. `/dev/ttyS2` must not be opened
while Bluetooth owns USART2.

## Service contracts

- Classic exposes SDP/RFCOMM channel 1 and the line-oriented protocol defined in
  [classic-protocol.md](../project/classic-protocol.md).
- BLE exposes the FD02 GATT protocol defined in
  [ble-protocol.md](../project/ble-protocol.md).
- Both map commands, telemetry, ownership, and disconnect handling through
  [hub-contract.md](../project/hub-contract.md).
- Responses outrank telemetry. Queues are bounded, and stale callbacks may not
  write into a later connection generation.
- A disconnect stops motors owned by that transport without stopping a newer
  owner.

## Lifecycle invariants

- One lifecycle owner performs reset, BTS streaming, baud changes, host start,
  recovery, and shutdown.
- Failed bootstrap never exposes a partially initialized host.
- eHCILL control bytes are consumed only at valid H4 boundaries.
- TX wake has a finite timeout; a latched timeout enters bounded recovery.
- ACL credits and buffers are finite. Exhaustion applies backpressure rather
  than allocating without bound.
- Settings writes use atomic replacement; invalid or incomplete bond data fails
  closed.

## Evidence and limitations

Native controller tests cover Classic and BLE connection lifecycles, ACL,
SDP/RFCOMM, ATT/GATT, basic SMP, disconnect, fragmentation, and error paths. The
Renode bridge acknowledges opaque vendor commands and lets the production image
reach daemon readiness.

Neither test executes TI controller firmware or proves RF, electrical timing,
physical pairing, host interoperability, or qualification. Those remain behind
the hardware gate in `SAFETY.md`.

## Operator surface

The daemon provides `start`, `stop`, `status`, and transport controls through
NSH. Protocol-specific usage is documented in
[bt-nsh-shell.md](../development/bt-nsh-shell.md) and
[pc-receive-spp.md](../development/pc-receive-spp.md). These commands are for
simulation until the hardware gate opens.
