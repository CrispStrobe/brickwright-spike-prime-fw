# Simulation-only arena guest

This newly authored BSD-3-Clause Cortex-M4 demonstration runs in Renode. It
contains no radio, physical-device driver, NuttX dependency or proprietary
firmware. It is an executable integration fixture, not full SPIKE firmware.

Build with `sh simulation/arena-demo/build.sh /tmp/brickwright-arena-demo`.
The ELF has no unresolved runtime symbols. Load the accompanying platform,
load the ELF, set the vector table to `0x08008000`, SP to `0x20050000` and PC
to the ELF's `reset_handler` symbol. Renode's platform timer is 72 MHz.

The fixed little-endian mailbox occupies 84 bytes at `0x20040000`. Fields are
32-bit words: signature BWAR (`0x42574152`), version 1, ticks (ms), input
sequence, distance (mm, -1 unknown), color ID, reflection percent, ambient
percent, force percent, pressed, load A percent, load B percent, position A
(millidegrees), position B, speed A (degrees/s), speed B, stalled A, stalled B,
output sequence, unloaded demand A (degrees/s), unloaded demand B.
Inputs are committed by odd/even input sequence; the guest adopts complete
frames at a timer interrupt. Output reads require the same even output sequence
before and after copying. Host input validation belongs to the bounded arena
input adapter. The mailbox is not a generic memory access interface.

A/B drive at -300/+300 degrees/s, with acceleration 2000 degrees/s² and
stopping deceleration 4000 degrees/s². Distance below 250 mm or pressed force
stops demand. Full load stops a motor immediately and sets stalled; partial
load scales its target speed. Color is observable but does not control motion.
Demand ends after one hour to keep signed position counters bounded. These
are synthetic rules, not physical calibration. Reset is required after the
supported one-hour observation interval.

Run the guest execution test with a Renode 1.16.1 installation and its Robot
requirements installed:

```
renode-test simulation/arena-demo/arena-demo.robot --variable PLATFORM:$PWD/simulation/arena-demo/arena-demo.repl --variable FIRMWARE:/tmp/brickwright-arena-demo/arena-demo.elf -r /tmp/brickwright-arena-guest-results
```

The test checks guest ticks and motion, commits a distance frame, waits for
stopping, and checks that the encoder stays still afterward. Artifacts belong
outside the public checkout. No emulator assets or ELF are checked in here.
