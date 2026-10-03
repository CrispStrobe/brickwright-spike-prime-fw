# SPIKE Prime instruction-level simulation

This directory boots actual STM32 firmware images. It does not replace the
existing transport/protocol simulator in Brickwright; the two gates answer
different questions.

The shared platform starts from Renode's STM32F4 peripheral model and adds the
SPIKE Prime memory map: the upper 64 KiB of the STM32F413VG's 320-KiB SRAM and
the 32-MiB W25Q256 address window. Target loaders always use the real vector
table at `0x08008000`.

## Target matrix

| target | local input | load form | first proof |
|---|---|---|---|
| `lego-v2` | user-supplied official legacy image | raw at `0x08008000` | valid vectors and PC leaves reset handler |
| `lego-v3` | user-supplied official modern image | raw at `0x08008000` | valid vectors and PC leaves reset handler |
| `spike-nx` | rebuilt from upstream commit `00524ea5464bddb46c852967e382f8f6b073abe6` | protected kernel and user images | symbol milestones |
| `brickwright` | rebuilt from this branch | protected kernel and user images | symbol milestones through daemon start |
| `brickwright-simulation` | rebuilt with the selected clean simulation profile | protected kernel and user images | local program startup; explicit HCI profile also tests Bluetooth startup |

## Image classes

| image | class | restricted component | who runs it |
|---|---|---|---|
| `brickwright-simulation` (`BOARD_CONFIG=simulation`) | clean | none; `tools/check_ti_free_image.py` reports 0/40 service-pack chunks | CI and local gates |
| `brickwright` built with `BOARD_CONFIG=usbnsh` | chip-restricted | TI CC2564C service pack 1.5 (`TIInit_6.12.26.bts`), 40/40 chunks, TI-device-only licence | never CI; a local run is the user's own action |
| `lego-v2`, `lego-v3` | user-supplied proprietary | the whole image is LEGO's; not inspected here, so treat any CC2564C initialization it carries as unknown and restricted | never CI; user-staged under `.local/` |
| `spike-nx` (rebuilt upstream) | chip-restricted | `apps/btsensor/chipset/cc256x_init_script.c`, copied from Pybricks (TI service pack 1.4), plus BTstack | never CI; local only |

CI builds two TI-free profiles in separate jobs and stages each under
`brickwright` and `brickwright-simulation`. `BOARD_CONFIG=simulation` keeps
Bluetooth autostart disabled and starts local program service independently.
`BOARD_CONFIG=simulation-hci` differs only by explicitly enabling
`CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI`; use it only with an attached virtual
controller. Each profile requires its own exact configured compiler/linker
inventory, checked before and after compilation. Profile switching requires a
clean build; an existing `.config` is never silently accepted as the other
profile.

The `brickwright-simulation-hci` gate tests the explicit HCI profile
against the virtual controller with `--reject-vendor`: no vendor command may
arrive, and the image still reaches `physical_load_firmware` (a no-op in this
profile), `physical_start_host`, `bt_enable`, `settings_load`, transport
registration, and the daemon-ready boundary, with the IMU and flash
initializers running against their bus models.

Official LEGO binaries are separately licensed inputs and
remain under ignored `.local/firmware-images/`. They are neither copied into
this repository nor uploaded by CI. Users must lawfully obtain and stage their
own files; the target manifest verifies known hashes before execution.

The public [gpdaniels/spike-prime snapshot](https://github.com/gpdaniels/spike-prime/tree/0b0c11f89cca61cf84b8d8e1ca0811ff05a5dc8b)
repository can be useful as an optional research and test reference. Its
author-created code is MIT, but its own README says files pulled from LEGO
firmware or filesystems remain licensed by LEGO. This project therefore does
not automatically fetch or vendor those files.

The production NuttX configuration exposes its console only over USB CDC.
Renode's F4 model does not provide a functional OTG FS device, so early tests
must use symbols, PC progress, and the fixed RAMLOG region. A diagnostic UART
build may aid debugging but cannot satisfy the unchanged-image gate.

The protected suite has two deliberately separate proofs. The unchanged image
must reach `stm32_bringup`. A second test then returns from that function at
the CPU hook boundary and requires `nsh_main`; this isolates and proves the
kernel-to-protected-userspace transition while the board peripherals are being
modeled. It is labeled as an isolated-boundary test and is not reported as an
unchanged full boot.

The MIT model layer attaches an LSM6DS3TR-C register subset at I2C2 address
`0x6a`, a command-level W25Q256JV behind the real PB12 chip-select path on SPI2,
and a TLC5955 digital register subset on SPI1 with PA15 as LAT. PA15 also retains
its SYSCFG connection. The private MIT Renode fork supplies request-paced
SPI/UART DMA behavior. The early `brickwright-board-models` milestone still
stops at display initialization; the TI-free existing-filesystem HCI gate runs
the actual display initialization and update functions through daemon readiness.
It reads the latched display state without changing guest registers.

The TLC5955 model follows TI's public
[SBVS237 digital interface](https://www.ti.com/lit/ds/symlink/tlc5955.pdf),
sections 8.3.2.1–8.3.2.7. Its 769-bit shift register retains bytes across SPI
transaction boundaries. A rising LAT commits grayscale data or a valid control
command; maximum-current fields require two matching control writes. Inspectable
registers distinguish chip output order from the firmware's serialized word
order. `brickwright-display-latch` tests real SPI1 accesses and GPIO edges with
synthetic vectors, including rejected commands, current confirmation and reset.

This subset returns zero on SPI reads and uses deterministic zero reset values
for otherwise unspecified control state. It does not model SOUT/status data,
analog current, active dot-correction timing or GSCLK/PWM waveforms. TIM12 keeps
its existing platform frequency; display-register qualification does not imply
correct grayscale-clock frequency or physical light output. The legacy stubbed
diagnostics and `simulation/bluetooth-air/test_spike_air.py` retain their explicitly
isolated display functions and are separate from this HCI qualification gate.

GPIO interrupt routing uses Renode's existing MIT `STM32_SYSCFG` model at
`0x40013800`. Each GPIO port feeds its own mux input, and the firmware's
EXTICR fields select the port forwarded to each EXTI line. The common F4
platform's direct fanout allowed PC9 Bluetooth-clock edges to trigger the PA9
VBUS handler. The `brickwright-exti-routing` regression exercises real model
connections: unselected-port edges are rejected, PA9 and PC9 can each be
selected, and write-one-to-clear removes both pending status and interrupt
output. This is a routing proof; complete Bluetooth startup is a separate gate.

TIM2's 96 MHz input and update TRGO drive ADC selector 6, matching the actual
board driver. Six stable synthetic inputs feed the model: battery current
0, battery voltage 3100, thermistor 2048, USB current 0, and both button
ladders 4095. These are 12-bit test inputs, not calibrated physical measurements.
Released buttons must be sampled through the configured ADC sequence and
DMA2 stream 0; a zero-filled buffer decodes as a ladder fault with the center
button flag and can trigger shutdown. The `brickwright-adc-dma` regression
uses scratch SRAM without loading firmware and checks actual timer-triggered
rank order, halfword writes, circular reload, completion clearing and voltage
changes representing button press/release. Guest buffer writes and power-button
function stubs are not used for this model proof.

The retained board-stub gate runs all of `stm32_bringup` while isolating the
same five synchronous initialization/update functions, then requires both
`nsh_main` and `hubprogram_main`. It remains explicitly labeled as a stubbed
diagnostic and must not be presented as peripheral-fidelity simulation.

The rebuilt original `spike-nx` protected pair also passes its unchanged reset,
`nx_start`, `board_late_initialize`, and `stm32_bringup` milestones. Its staged
kernel is 221,180 bytes (SHA-256 `31852ec0ba70c6f66fa16ed56b14c3226598121b7f40cc607aa61b6fb1ef77b0`)
and its user image is 401,192 bytes (SHA-256
`fcabc6e45354092432f3db777dc86b0a96a1f2337701c685155ebce50ceed8c7`).
These locally built images remain ignored inputs.

The platform is deliberately incomplete. Clock fidelity, the remaining
synchronous board bring-up, LPF2 devices, and USB are tracked in `PLAN.md` C8. A
passing emulator run is never evidence for RF behavior, TI service-pack
semantics, electrical behavior, or physical timing.

Flash scenarios distinguish erased-media first boot from explicitly loaded,
synthetic existing filesystems. CI retains the erased-media board gate and
selects separate normal-boot board/HCI tags. The fixture is generated from the
exact qualified LittleFS sources, validated and programmed through public NOR
SPI commands while paused before guest execution; default reset remains
unchanged. See the
[fixture provenance and coverage record](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/docs/project/synthetic-littlefs-fixture.md)
for tag names, lifecycle and limits. Generating this fixture alone provides no
guest-boot qualification.

The protected suite's milestone waiter synchronously stops emulation, arms its
log predicate before allowing the waiter's internal start, and stops again
before inspecting registers. An explicit start followed by a log wait could
restart an already stopped CPU when the notification was delayed. The
`brickwright-milestone-wait` regression uses separate synthetic Cortex-M
instructions and controlled host-delayed logging to demonstrate the old
restart and verify that the shared helper retains the actual captured state.
It also joins its log producer before resetting the test machine. This fixture
contains no firmware image or extracted implementation.

## Virtual HCI boundary

`tools/test_renode_virtual_hci_bridge.sh` builds and tests a small Apache-2.0
TCP controller process around the same `virtual_hci`/H4 implementation used by
the native simulator. Renode's raw `ServerSocketTerminal` connects it directly
to `sysbus.usart2`. Vendor HCI commands have an explicit opt-in acknowledgement
policy: their payload is not parsed, interpreted, retained, or executed. This
allows an opaque, locally supplied TI bootstrap stream to cross the simulated
controller boundary without making the bridge an implementation of TI
firmware.

Set `BRICKWRIGHT_RENODE_FIRMWARE_TEST=1` to run the protected-image boundary
test after the standalone socket test. Build the explicit TI-free
`simulation-hci` profile and use the source-built custom Renode fork. The test
crosses `physical_open`, `physical_load_firmware` (a no-op in this profile),
and `physical_start_host`; it sends standard HCI commands to a controller
configured with `--reject-vendor` and streams no TI service pack. The fork
models RX/TX request routing, request persistence across stream setup, circular
NDTR reload, and USART IDLE behavior. The gate continues through `bt_enable()`,
`settings_load()`, hub-transport registration, and the daemon's ready-to-wait
boundary. A linker regression check ensures that the Zephyr net-buffer pool
table remains inside NuttX's protected initialized-data range.

## Local run

```sh
tools/install_renode.sh
# Stage lawfully obtained images under .local/firmware-images/.
tools/test_renode_opaque_images.sh
# After staging both NuttX builds with tools/stage_nuttx_image.py:
tools/test_renode_protected_images.sh
tools/test_renode_virtual_hci_bridge.sh
```

For the custom qualification gates, build the pinned fork from source and
export both paths reported by its installer:

```sh
tools/install_renode_fork.sh
export RENODE_DIR="$(tools/install_renode_fork.sh --print-runtime)"
export RENODE_TEST_VENV="$(tools/install_renode_fork.sh --print-venv)"
# After staging the corresponding clean protected pairs and generating
# .local/firmware-images/existing-filesystem with tools/make_littlefs_fixture.py:
tools/test_renode_protected_images.sh \
  --variable "PLATFORM:@$PWD/simulation/renode/spike-prime-custom-dma.repl" \
  --include brickwright-existing-filesystem-board
BRICKWRIGHT_RENODE_FIRMWARE_TEST=1 \
BRICKWRIGHT_RENODE_TAG=brickwright-simulation-hci-existing-filesystem \
  tools/test_renode_virtual_hci_bridge.sh
```

The board command uses the default `simulation` pair staged as `brickwright`;
the HCI command uses the separately built `simulation-hci` pair staged as
`brickwright-simulation`. The existing-filesystem tags explicitly load the
synthetic fixture and do not replace the erased-media first-boot gate.

The fork source and model tests live in the public repositories
`CrispStrobe/renode-spike-prime` and
`CrispStrobe/renode-infrastructure-spike-prime`. The HCI script selects
`spike-prime-custom-dma.repl`; the default `spike-prime.repl` deliberately
remains loadable by pinned stock Renode for the bounded public-model gates.

All local image staging remains below ignored `.local/` paths.
