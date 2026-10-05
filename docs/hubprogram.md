# Autonomous programs and embedded Python

The `hubprogram` application runs inside the protected NuttX userspace. It
uses `/dev/legoport*` for discovery, mode selection, encoder samples and PWM;
the host does not supply motor positions or execute the program instructions.
Motor commands accept physical ports A–F (integer indices 0–5) when the
attached device reports a supported motor type (46, 48, 49 or 65). Missing
ports, unsynchronized discovery and wrong device types return driver errors;
a motor command never changes an attached sensor into a motor. The sensor API
retains color/reflection C, distance D and force-button E. It is a bounded API,
not complete SPIKE Python compatibility.

The simulation profile starts local program execution independently of radio
startup. Its TI-free default leaves the Bluetooth daemon stopped: no HCI
controller is attached by the motor/sensor arena. A separately configured
virtual-controller run can opt in with `CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI=y`,
with the controller connected before boot. The option does not create a
controller or establish Bluetooth compatibility. Physical firmware retains
its Bluetooth startup. Both the simulation and USB NSH profiles include the
application. USB NSH accepts
`hubprogram packet HEX`, where HEX encodes one 8–20 byte protocol request.
The modern BLE service accepts the identical packet and returns its 20 byte
reply. An emulator-only, ELF-resolved debug mailbox submits packets to the same
service for offline tests. This mailbox does not replace the port drivers.
Stopping the daemon cancels its program; losing a transport connection alone
does not terminate an autonomous program.

## Program and timing contract

Instruction programs contain 1–256 rows of four signed little-endian 32-bit
words, `op,a,b,c`. Supported operations are END (0), continuous speed (1),
wait (2), wait for sensor (3), jump (4), conditional sensor jump (5), and
relative motor position (6). The final row must be END. Speeds use degrees per
second, positions degrees, waits milliseconds, distance millimeters, color
IDs and reflection percentages. Speed magnitude is at most 1110; relative
positions are at most 36000 degrees. Motor port operands are 0–5 in both
native instructions and Python calls.
Python retains `b.A` and `b.B`; use integers 2–5 for C–F.
Positions block the instruction stream
while another motor's earlier continuous command can remain active.

The worker runs every 10 milliseconds using NuttX monotonic time. In Renode
this clock is driven by simulated hardware time. Zero-duration waits yield;
32 immediate instructions per tick prevent a jump loop starving the service.
Programs time out after 120 simulated seconds. Unknown/stale sensor samples
cannot satisfy a condition. Driver errors terminate execution and attempt to
brake only the motors owned by the program. END waits for those motors to stop.
The version-1 debug snapshot still contains only motors A/B. The current
arena wiring remains A/B motors and C/D/E sensors; host device-IO fixtures
cover other attached-motor layouts without claiming six-motor Renode coverage.
There is no position-hold guarantee after the devices are released.

Encoder-feedback control ramps the reference, applies a bounded PWM demand,
and slows as the relative position target approaches. Position completion
requires three stationary samples within one degree and 20 degrees/second.
A stalled motor cannot complete a position merely because time elapsed.
Controller constants and emulator load dynamics are synthetic policies;
physical calibration and full control-system equivalence are not established.

## Python

An embedded MicroPython v1.26.1 compiler/VM executes uploaded UTF-8 source,
including functions, loops, lists and comprehensions. It has a 32 KiB GC heap,
a 16 KiB worker stack, cooperative cancellation and the same 120 second limit.
Only one VM executes at a time. Source cannot change until a stopped VM unwinds.
Filesystem imports, file I/O and networking are not provided by this port.

```python
import brickwright as b
b.motor(b.A, 400)
b.position(b.B, -90, 500)
b.sleep_ms(100)
distance = b.sensor(1)
```

`position` waits for encoder feedback. Sensor selectors 1/2 read distance D,
3 reads pressed E, 4 color C, and 5/6 reflection C. An unavailable sensor raises
`OSError`; the program may retry. The low-level Python module is separate from
the original LEGO Python modules.

## Transport contract

Requests begin with `70 01 OP 00` followed by a nonzero little-endian program
ID. STATUS permits ID zero as a wildcard. BEGIN (0) adds instruction count and
CRC-32/ISO-HDLC; BEGIN_PYTHON (7) adds source byte length and CRC instead.
Both are 16 bytes. CHUNK (1) adds a 16-bit byte offset and 1–10 payload bytes.
COMMIT (2), START (3), STOP (4), STATUS (5), ABORT (6), SAVE (8) and
LOAD (9) are exactly eight bytes.

Uploads are contiguous and bound to one transport owner and ID. Identical
chunk retries are accepted. Conflicting or out-of-order chunks fail. Staging
expires after 30 seconds. COMMIT checks completeness, CRC and instruction
bounds before replacing the committed program. Python is limited to 4095
bytes and cannot contain NUL. Active programs reject replacement.

Replies are 20 bytes: `71 01 OP STATE`, ID, signed 32-bit request result,
16-bit PC, count, received byte count and signed 16-bit runtime error. Fields
are little-endian. The ID echoes the request, except wildcard STATUS returns
the committed ID. States are EMPTY=0, READY=1, RUNNING=2, COMPLETE=3, STOPPED=4,
FAULT=5. Results use negative errno values. Count means instructions for an
instruction program and source bytes for Python.

START accepts a retained program in READY, COMPLETE, STOPPED or FAULT. It starts
from the beginning with fresh execution state and a new bounded deadline;
re-upload or LOAD is unnecessary. Concurrent START, a wrong ID or an invalid
deadline fails without modifying the active program. Genuine MicroPython
`OSError` values preserve device, cancellation and timeout errno in the runtime
result; syntax and malformed exceptions remain `-EINVAL`.

## Explicit program persistence

SAVE (8) writes the committed program with the matching nonzero ID to the
single firmware-controlled path `/mnt/flash/brickwright.program`. LOAD (9)
requires that saved ID and restores the program to READY; it does not run it.
There is no automatic load or execution on boot. USB NSH, the modern transport
and the debug mailbox all use the same service mutex and fixed slot. Both
operations reject a running program, an active upload or an unwinding Python
VM with `-EBUSY`. Packet fields cannot select filesystem paths.

The portable storage record has a 20-byte header: magic `BWP1`, version 1,
language (0 native, 1 Python), two zero reserved bytes, little-endian ID,
count and payload length. Native payloads contain the same signed
little-endian instruction words as uploads; Python payloads contain source
bytes without NUL. A final CRC-32/ISO-HDLC covers both header and payload.
Loads reject corrupt, truncated, oversized, trailing or semantically invalid
records before changing the committed program. A mismatched ID returns
`-ENOENT`. Reads and writes allocate at most one 4120-byte record plus a short
temporary path; they do not add a large static buffer or stack allocation.

Saving writes a temporary sibling file, synchronizes and closes it, then
renames it over the slot. Errors leave the committed in-memory program
unchanged. Host tests verify that failure to create the temporary file also
preserves the previous slot. The full ARM firmware also saved native and completed Python programs on
LittleFS; separate Renode processes restored their flash snapshots, loaded
each program to READY and executed it successfully. The pinned real LittleFS
crash/restart harness also covers 426 interrupted-write cases for program
replacement. Physical flash behavior and wider filesystem operations remain
unqualified. Python file I/O remains
unavailable; persistence is an explicit service operation.

## Memory and licences

The physical 1 MiB flash retains its first 32 KiB bootloader region, then
allocates 352 KiB to the kernel and 640 KiB to userspace. ARMv7-M MPU subregions
exclude the kernel/bootloader from the userspace mapping. There is no flash
region beyond `0x08100000`. Static userspace RAM remains capped at 96 KiB.
The profiles use 16 telemetry queue slots to leave heap space for Python.

New application components use BSD-3-Clause; see `apps/hubprogram/LICENSE`.
The vendored MicroPython embed package retains its MIT licence and source
notices, with its pin and generation recipe in `third_party/micropython-embed/UPSTREAM.txt`.
Existing firmware and dependency notices remain applicable and unchanged.
Normal builds use the checked-in embed source package and do not fetch Python
or a firmware image. Regenerating that package requires the pinned upstream
checkout and a fresh `build-embed` directory, because generator caches depend
on the port configuration.

## Validation

Run `tools/check_hubprogram.sh` for sanitizer-backed portable interpreter,
upload, storage corruption/truncation and replacement-failure tests, device/controller tests and a real host MicroPython VM execution test.
Run `python3 tools/check_resource_budgets.py --elf nuttx/nuttx_user.elf` after
building the full protected simulation profile. The ARM build and budget
checks do not establish a functioning USB/BLE connection or successful robot
execution in an emulator. Those require separate full-machine integration
tests; boot, peripheral negotiation, firmware execution and GUI/arena wiring
must each be qualified before their capability is advertised.

The boot script runs `hubprogram serve` before radio startup. This initializes the same persistent program service used by the packet CLI, modern hub transport and simulation mailbox, so a missing radio does not prevent local program execution.

With `CONFIG_APP_HUBPROGRAM`, the boot script does not automatically start the separate drivebase daemon, which would claim motor A/B. Its manual CLI remains available; conflicting port ownership returns an error.


### Renode integration qualification (2026-10-02)

The full protected ARM image has now booted with five negotiated LPF2 devices.
Tests ran sequential uploads, embedded Python arithmetic and exceptions,
infinite-loop cancellation, continuous motor motion and braking, relative
position completion, concurrent motor/sensor waits, arena force input, load
stall and cancellation. The GUI upload codec and arena session also drove
actual ARM execution over the bounded loopback state service, followed by a
new program after cancellation. A synthetic 30-degree position move measured
28.10 degrees; this case uses a three-degree relative tolerance. These tests
qualify the stated synthetic model, not physical hub accuracy or complete
LEGO firmware/API compatibility.

Python output is kept in a 1024-byte buffer and truncated on overflow; it never
blocks on an absent USB/BLE console. Each VM execution clears the buffer.
Host VM tests exercise output overflow followed by another execution.

The SPI/DMA follow-up qualified blank external flash formatting and mounting
in Renode. That does not yet qualify program-file persistence.

Remaining integration gaps include USB OTG transport, an actual Bluetooth
radio/link, power-loss recovery and wider filesystem operations, runtime MPU isolation qualification,
and wider long-duration and resource-exhaustion tests. Original LEGO and
upstream LEGO_HUB_NO6 MicroPython images have only bounded CPU startup probes;
no original-firmware robot-program or peripheral compatibility is claimed.
Private image inputs, generated run records and complete transcripts remain
outside public repositories.

The exported `g_bw_program_storage_abi` value 1 advertises the fixed-slot
SAVE/LOAD contract. Consumers must verify this value in the running firmware;
older images without the symbol do not advertise storage support. This does
not change the version-1 debug transport or its two-motor snapshot layout.

Fresh virtual flash can be initialized with
`python3 tools/make_simulation_littlefs_seed.py NEW_OUTPUT_FILE`. The tool
requires the reviewed retained LittleFS sources and the matching configured
simulation tree. It compiles a small host formatter in `TMPDIR`, formats via
LittleFS v2.5.1, and verifies a read-only mount and empty root before creating
an output file. Existing files are never overwritten. The seed is exactly
8192 bytes: the first two 4096-byte superblocks of the mounted partition.
Load it at chip offset `0x100000`, preserving the reserved first MiB; the
partition has 7936 erase blocks within the 32 MiB W25Q256. The driver reports
256-byte MTD pages, and the configured LittleFS read/program/cache factor of
four gives 1024-byte operations. The remaining virtual flash must initially
read as `0xff`; Renode's `GenericSpiFlash` sets its `MappedMemory.ResetByte`
to that erased value. Do not apply an empty seed to an existing flash image.
This fresh-image initialization leaves firmware mount failure and nonblank
flash preservation unchanged. Full blank-chip scanning remains a separate
boot qualification; the seed avoids that 31 MiB scan during routine fresh
virtual boots.

The audited simulation policy declares `capabilities.motorPorts: 6` for this
qualified own build. The package generator may use it to offer an optional
six-motor sandbox profile; storage ABI alone is not a topology declaration.
The actual A–F sequence passed 207 observations with speed, relative position,
concurrent activity, native/Python cancellation and a run beyond 12 seconds.
The largest position error was 1.73 degrees against the existing 3-degree
bound. These are simulated observations, not physical calibration evidence.
