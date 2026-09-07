# Other LEGO hubs and the PBIO relationship

This note records candidate NuttX targets beyond the SPIKE Prime hub. It is a
planning assessment, not a claim that any listed brick is safe to flash. Every
new target remains **simulation only** until its own recoverability and
hardware-validation gate is completed.

## Recommended target order

| Priority | Target | Verified platform evidence | NuttX assessment |
|---|---|---|---|
| 1 | SPIKE Essential Hub | STM32F413, 1 MiB internal flash, 320 KiB SRAM, LSM6DS3TR-C | Best second port. It should reuse most of the Prime STM32F4, IMU, LPF2, protocol, and simulator work. |
| 2 | Technic/Control+ Hub 88012 | STM32L431, 256 KiB flash, 64 KiB SRAM, four LPF2 ports, LSM6DS3TR-C, external CC2640 | Best different modern hub. NuttX supports STM32L4; memory requires a smaller configuration than Prime. |
| 3 | City Hub 88009 | STM32F030, 256 KiB flash, 32 KiB SRAM, two LPF2 ports, external CC2640 | Feasible as a deliberately small flat build. It should not promise Prime feature parity. |
| 4 | BOOST Move Hub | STM32F070, 128 KiB flash, 16 KiB SRAM, integrated motors, BlueNRG radio | Research/footprint target only. It needs static buffers, few services, and probably no shell or filesystem. |
| 5 | Prime/Robot Inventor H5 revision | STM32H562, 1 MiB flash, 640 KiB SRAM | A separate high-capacity Prime-family BSP and simulator machine because clock, security, and boot behavior differ. |
| 6 | EV3 | TI AM1808 ARM9, 64 MiB DDR, 16 MiB flash, microSD recovery path | Plenty of capacity and safely bootable from microSD, but current NuttX has no AM1808/DA850 port. Treat as a separate SoC project. |
| 7 | RCX | Hitachi/Renesas H8/3292 at 16 MHz, 32 KiB ROM, 32 KiB RAM | A plausible minimal-RTOS research port, but current NuttX has no H8/300 architecture port. Historical brickOS code is GPL and is not reusable here. |
| 8 | NXT | AT91SAM7S256 ARM7, 256 KiB flash, 64 KiB RAM, AVR I/O coprocessor | Technically plausible but requires substantial obsolete-SoC and coprocessor work for limited leverage. |
| 9 | Mario/Luigi/Peach figures and Powered Up remote | BLE peripheral behavior is known; precise recoverable firmware platform details are incomplete | Model as peripherals first. Do not attempt replacement firmware without verified MCU, boot, signing, and recovery evidence. |

The recommended expansion sequence is Essential, Technic, City, then Move.
EV3 and RCX belong in separate architecture research tracks.

## Radio boundary

Several smaller hubs use a second controller containing proprietary radio
firmware: CC2640 on City/Technic and BlueNRG on Move Hub. A permissively
licensed NuttX host may communicate with an already installed controller image,
but that does not grant a right to copy, modify, or redistribute controller
firmware. Each radio therefore needs the same explicit boundary used for the
CC2564C work:

1. keep the host transport and protocol code permissively licensed;
2. treat controller firmware as an opaque, separately licensed component;
3. do not vendor or update it until redistribution terms and exact hashes are
   established; and
4. never represent simulator behavior as RF, electrical, or controller-
   firmware validation.

USB-only and simulator-first board ports do not depend on resolving controller
redistribution.

## What Pybricks is

Pybricks is a family of MicroPython device ports, not an RTOS distribution.
Its useful architectural layers are:

1. hub-specific startup, linker layout, boot/update integration, and drivers;
2. PBIO, the C device/control/protocol layer, whose Pybricks-authored files are
   commonly MIT-tagged but whose usable build closure is not automatically
   MIT-only;
3. C implementations of the `pybricks` Python modules over PBIO; and
4. the MicroPython VM that executes user programs.

Current Pybricks uses its own lightweight cooperative protothread/event
machinery rather than placing MicroPython on NuttX. Its platform definitions
and tests are strong independent evidence for memory maps, peripheral wiring,
device semantics, and expected control behavior.

## PBIO reuse policy

PBIO can be used in three increasingly coupled ways:

### 1. Behavioral oracle — default

Use independently written fixtures to compare our neutral hub contract,
protocol responses, sensor conversions, and motor behavior with Pybricks on the
same deterministic inputs. Do not copy implementation merely to make a test
pass. Record the exact Pybricks commit used as evidence.

### 2. Selective source reuse — allowed only after closure review

Only individual PBIO files carrying the Pybricks MIT SPDX/copyright header may
be presumed MIT, and even then their included/generated/linked dependencies
must be traced. MIT-tagged algorithms or device parsers may be ported when they
are materially better than a new implementation. Preserve copyright and SPDX
notices, record file-level provenance, include them in the SBOM/link map, and
adapt them behind the neutral hub API.

The repository licence explicitly says that its MIT grant applies only to
files with the stated header. A built Pybricks firmware inherently includes
other licences. Known examples include BTstack terms that prohibit charging,
GPL-2.0 nxos in the NXT platform, proprietary/BSD TI BLE5 material, and
proprietary STM32 BlueNRG material. Therefore neither the repository, the PBIO
directory, nor a Pybricks firmware binary may be labelled MIT as a whole.
BTstack, GPL-family code, and noncommercial/restrictive components are excluded
from this project's source and link closure.

Likely candidates are pure motor-control mathematics, observers, LPF2 device
parsers, unit conversions, and protocol codecs. Their clocks, allocation,
locking, and callbacks must be supplied by a small NuttX adaptation layer and
must not bypass NuttX safety/lifecycle ownership.

### 3. Wholesale PBIO platform port — not the default

It is technically possible to run PBIO over NuttX, but importing its complete
platform layer would overlap NuttX scheduling, device drivers, Bluetooth,
storage, and lifecycle services. That creates two competing hardware and event
abstractions. Consider it only after a measured prototype demonstrates a clear
flash/RAM, correctness, or maintenance advantage.

The transport-neutral hub contract remains authoritative regardless of reuse.
This allows NuttX-native services, selectively reused PBIO components,
Brickwright, and Renode to share conformance fixtures without becoming coupled
to MicroPython.

## Evidence pinned for follow-up

- [Pybricks source and per-hub platform definitions](https://github.com/pybricks/pybricks-micropython/tree/6ab0d3b2a594d3e46c4c8db5c574fc76123f70f8)
- [Pybricks file-scoped licence warning](https://github.com/pybricks/pybricks-micropython/blob/master/LICENSE)
- [Pybricks third-party licence inventory](https://github.com/pybricks/pybricks-micropython/blob/master/3RD_PARTY_NOTICES.md)
- [NuttX STM32 family support](https://github.com/apache/nuttx/blob/2a6a86cb68d9e665580aadc395707af002ed1ac5/Documentation/guides/stm32_ports.rst)
- [LEGO EV3 firmware developer kit](https://www.lego.com/cdn/cs/set/assets/blt77bd61c3ac436ea3/LEGO_MINDSTORMS_EV3_Firmware_Developer_Kit.pdf)
- [EV3 non-destructive microSD boot](https://www.ev3dev.org/docs/getting-started/)
- [RCX H8/3292 hardware notes](https://www.classes.cs.uchicago.edu/archive/2006/winter/23000-1/docs/handout-03.pdf)
- [Mario-family protocol research](https://github.com/bricklife/LEGO-Mario-Reveng)
