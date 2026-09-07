# Local NuttX integration constraints

The project patches its pinned NuttX fork and does not file upstream issues as
part of this work. Keep changes minimal and record any changed pin in provenance.

## Bluetooth UART

The pinned STM32 generic HCI UART path is not used. The board-local
`stm32_btuart.c` lower half owns CC2564C USART2, DMA, flow control, power, and
clock resources and presents the project H4 seam.

NuttX Kconfig requires an USART2 role. The configuration retains the serial
driver selection, after which the board Bluetooth lower half reconfigures the
peripheral. `/dev/ttyS2` remains registered and must not be opened while the
Bluetooth lifecycle owns USART2.

The upstream CC2564 loader contains no usable controller payload. This project
does not populate it. The lifecycle instead streams the exact separately
licensed TI service pack through the board-local seam and handles eHCILL on the
host. See [Bluetooth architecture](../drivers/bluetooth.md) and
[TI service-pack boundary](../project/ti-service-pack.md).

## Review rule

Before changing the fork, prove that the board layer or project compatibility
layer cannot express the fix cleanly. Test the exact configured target and keep
generic changes separable so they can be rebased or proposed upstream later.
