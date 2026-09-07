# Brickwright SPIKE Prime firmware

> **WARNING — SIMULATION-ONLY WORK IN PROGRESS**
>
> This Brickwright firmware derivative is not yet safe to install on a physical
> SPIKE Prime Hub. It has not completed the required real-hardware electrical,
> motor-safety, power-loss, thermal, radio, recovery, and long-duration tests.
> Use it only in the supported Renode simulation. Do not flash any image built
> from this repository to real silicon. See [SAFETY.md](SAFETY.md).

This project ports the SPIKE Prime Hub to NuttX and provides applications,
host tools, protocol documentation, and a Renode-based validation environment.

## Current implementation state

The protected NuttX image builds with the transport-neutral Classic/BLE host,
boots in the custom Renode fork, initializes external flash and DMA, streams a
lawfully supplied opaque TI service pack to the simulated H4 controller,
completes `bt_enable()`, and reaches the daemon-ready boundary. Official LEGO
v2/v3, Pybricks, original spike-nx, and Brickwright images also have bounded
vector/instruction-progress gates.

This is meaningful firmware execution, but it is not yet full hardware
validation. Radio RF behavior, physical motors and sensors, electrical and
thermal limits, recovery from interrupted updates, and long-duration operation
remain outside the completed evidence.

## Benchmark results

| Board | MCU | CoreMark | CoreMark/MHz | Compiler | Flags |
| --- | --- | ---: | ---: | --- | --- |
| SPIKE Prime Hub | STM32F413VG (96 MHz) | 171.19 | 1.78 | GCC 13.2.1 | `-Os` |
| B-L4S5I-IOT01A | STM32L4R5VI (80 MHz) | 143.16 | 1.79 | GCC 13.2.1 | `-Os` |

## Simulation quick start

Build the default NuttX configuration:

```bash
make
```

Install the pinned Renode release and run the protected-image suite:

```bash
tools/install_renode.sh
tools/test_renode_protected_images.sh
```

Local official/Pybricks image tests are opt-in, ignored, and hash-verified:

```bash
tools/test_renode_opaque_images.sh
```

The repository never fetches or uploads those firmware images.

## Physical hardware status

Physical-hardware flashing is unsupported and unsafe until the
hardware-validation gate in [SAFETY.md](SAFETY.md) is complete.

## File transfer with picocom and Zmodem

The external W25Q256 (32 MB SPI NOR) is mounted at `/mnt/flash`. Install
`lrzsz` and use picocom to transfer files between the PC and Hub.

Upload from PC to Hub:

```bash
picocom --send-cmd 'sz -vv -L 256' /dev/tty.usbmodem01
```

Enter `rz` at the NSH prompt, press `Ctrl-A Ctrl-S`, select the local file,
and wait for completion. The file is saved as `/mnt/flash/<basename>`.

Download from Hub to PC:

```bash
cd <destination-directory>
picocom --receive-cmd 'rz -vv -y' /dev/tty.usbmodem01
```

Enter `sz /mnt/flash/file.bin` at the NSH prompt, then press `Ctrl-A Ctrl-R`
and Enter without an argument. Exit picocom with `Ctrl-A Ctrl-X`.

Use `sz -L 256`; USB CDC has no hardware flow control and larger default
subpackets can trigger ZNAK retries. Do not use `-e`, because USB CDC is
8-bit clean. See the [file-transfer guide](docs/en/development/file-transfer.md)
and [flash-storage guide](docs/en/usage/01-flash-storage.md).

## NSH shell over Bluetooth

Issue #108 adds mutually exclusive `MODE SHELL` and `MODE TELEMETRY` modes
over SPP RFCOMM. Start the service from USB NSH:

```text
nsh> btsensor start
nsh> btsensor bt on
```

Record the Hub address from `HCI working, BD_ADDR XX:XX:...` in `dmesg`, pair
and trust it with `bluetoothctl`, then connect RFCOMM channel 1:

```bash
sudo rfcomm connect 0 E0:FF:F1:5A:30:35 1
sudo picocom -l --echo --omap crlf --imap lfcrlf /dev/rfcomm0
```

Send `MODE SHELL` to enter NSH and `exit` to return to telemetry mode. Entering
shell mode stops the IMU and sensor pumps; send `IMU ON` or `SENSOR ON` after
returning if needed. Ctrl-C and job control are unavailable because the FIFO is
not a tty; disconnect RFCOMM to stop a long-running command.

See the [Bluetooth NSH shell guide](docs/en/development/bt-nsh-shell.md) and
[SPP/RFCOMM pairing guide](docs/en/development/pc-receive-spp.md).

## Documentation

All maintained documentation is in [docs/en](docs/en). Build it with MkDocs:

```bash
mkdocs build --strict
```

License and redistribution boundaries are documented in [LICENSE](LICENSE),
[NOTICE](NOTICE), and [THIRD_PARTY.md](THIRD_PARTY.md).
