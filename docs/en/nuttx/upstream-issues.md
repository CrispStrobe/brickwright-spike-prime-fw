# Known upstream NuttX issues

Issues we have noticed while reading the NuttX submodule (owhinata's fork of 12.13.0) in the course of this project.  We do not open issues against apache/nuttx — see memory `feedback_no_nuttx_upstream_issues.md` — and instead keep notes here.  When fixes are necessary, we patch the owhinata/nuttx fork.

## Bluetooth UART: compile blockers in `stm32_hciuart.c`

**File**: `nuttx/arch/arm/src/stm32/stm32_hciuart.c`

Enabling `CONFIG_STM32_USART*_HCIUART` + `CONFIG_STM32_HCIUART_RXDMA` pulls this file into the build, and static reading surfaces multiple compile blockers:

| Line | Problem |
|------|---------|
| L1095 | `rxnext = 0` — missing trailing semicolon |
| L2409 | `config.state->rxdmastream` — `config` is a pointer; should be `config->state->...` |
| L2434 | `handled = true;` — `handled` is undeclared |
| L2661-2666 | `g_hciusart1_config.state`, `g_hciusart2_config.state` — same pattern |

Each is an in-file typo that stays dormant upstream because nobody flips the CONFIG.

**Workaround in this project**: Issue #47 (CC2564C Bluetooth) avoids `stm32_hciuart.c` entirely and provides a board-local `struct btuart_lowerhalf_s` in `boards/spike-prime-hub/src/stm32_btuart.c`.  See [Bluetooth driver](../drivers/bluetooth.md).

## Bluetooth UART: missing firmware in `bt_uart_cc2564.c`

**File**: `nuttx/drivers/wireless/bluetooth/bt_uart_cc2564.c`

Lines 48-58 declare `cc256x_firmware[]` / `ble_firmware[]` with `#warning` annotations as zero-filled arrays.  The user has to hand-edit the firmware bytes into the file before anything works.  (Shipping the actual TI `.bts`-derived blob upstream is awkward because of SPDX/licensing considerations.)

`btuart_create()` at L163-209 unconditionally calls `load_cc2564_firmware()`, which immediately fails the size check at L135-138:

```c
if (sizeof(cc256x_firmware) < 10 || sizeof(ble_firmware) < 10)
  {
    return -EINVAL;
  }
```

**Current project boundary**: the old Pybricks-derived v1.4 array was removed.
The host uses the board-local HCI UART seam and streams only the allowlisted,
byte-exact TI CC2564C v1.5 BTS from `third_party/ti-cc2564c/`; its adjacent TI
licence remains separate from the project licence. eHCILL is handled by host
transport code, never by patching TI bytes.

## USART2 Kconfig choice is mutually exclusive

**File**: `nuttx/arch/arm/src/stm32/Kconfig` L9825-9846

`CONFIG_STM32_USART2=y` forces a 3-way Kconfig choice between `STM32_USART2_SERIALDRIVER`, `STM32_USART2_1WIREDRIVER`, and `STM32_USART2_HCIUART`; `STM32_USART2_SERIALDRIVER` is the default.  When we want USART2 as a dedicated Bluetooth HCI UART:

- `HCIUART` triggers the compile blockers above.
- `SERIALDRIVER` leaves `stm32_serial.c` responsible for configuring USART2 and registering it as `/dev/ttyS2`, racing the board-local driver for the same register set.
- `1WIREDRIVER` is for 1-Wire hosts — unrelated.

**Workaround in this project**: We keep `SERIALDRIVER` selected (Kconfig default) and let the board-local `stm32_btuart.c` reprogram USART2 after `arm_serialinit()` has run.  `/dev/ttyS2` remains registered but nothing should open it once Bluetooth is live.  The file header of `stm32_btuart.c` documents this coexistence.

## References

- Memory: `feedback_no_nuttx_upstream_issues.md` — no Issue filings against apache/nuttx; patch the fork if necessary
- Memory: `feedback_nuttx_minimal_changes.md` — keep submodule changes minimal
