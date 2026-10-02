# Simulation-only arena guest

This newly authored BSD-3-Clause Cortex-M4 guest runs in Renode. It
contains no radio, physical-device driver, NuttX dependency or proprietary
firmware. It executes a bounded instruction format and retains a built-in demonstration.
It is simulation firmware, not the full NuttX build or a Python interpreter.

Build with `sh simulation/arena-demo/build.sh /tmp/brickwright-arena-demo`.
The ELF has no unresolved runtime symbols. Load the accompanying platform,
load the ELF, set the vector table to `0x08008000`, SP to `0x20050000` and PC
to the ELF's `reset_handler` symbol. Renode's platform timer is 72 MHz.
The guest platform instantiates only Renode's MIT-licensed Cortex-M4, NVIC,
RAM and flash models. It does not load the full STM32 platform or fetch SVD
register descriptions. Full firmware platforms elsewhere remain unchanged.

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

The program mailbox at `0x20041000` is 4,124 bytes: signature BWPG
(`0x42575047`), version 1, commit sequence, instruction count, status, program
counter, error, then up to 256 four-word signed instructions. Status is 0
(unloaded), 1 (running), 2 (completed), or 3 (failed). Errors are 1 (header),
2 (120-second guest-time limit), 3 (program counter), 4 (invalid instruction).
An odd sequence is uncommitted. The host pauses the guest for a validated
single upload and publishes even sequence 2 last. A new owned session is
required for another program. Reset clears both mailboxes.

| Opcode | a | b | c | Behavior |
| --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | END: brake both motors and complete once stationary |
| 1 | motor 0=A, 1=B | -1110…1110 deg/s | 0 | Set continuous speed demand |
| 2 | 0…120000 ms | 0 | 0 | Wait in guest time; motors continue |
| 3 | sensor condition | threshold | 0 | Wait until condition holds |
| 4 | instruction index | 0 | 0 | Jump |
| 5 | sensor condition | threshold | instruction index | Jump if true, otherwise advance |
| 6 | motor 0=A, 1=B | -36000…36000 degrees | 1…1110 deg/s | Relative position move, waiting for arrival |

Sensor conditions: 1=distance D below threshold, 2=distance D above threshold
(0…65535 mm; unknown -1 never matches), 3=force E pressed equals 0/1,
4=color C equals 0…255, 5=reflection C below 0…100, 6=reflection C above
0…100. Only these mounted sensors and A/B motors are supported.

Execution is capped at 32 nonblocking instructions per 1 ms timer interrupt.
A zero wait yields one interrupt. Continuous commands for both motors issued
in one interrupt act concurrently. Waits/loops keep the motors running.
Position moves use stopping-distance speed control and clamp the final
millidegree encoder increment; they block the program while the other motor
can continue. Full load stalls; stalled position moves wait until released
or the global timeout. END brakes with 4000 deg/s²; acceleration is
2000 deg/s². Coasting, HOLD, display, sound, variables and arbitrary Python
are outside this contract. All dynamics remain synthetic.

`cc -std=c99 -Wall -Wextra -Werror simulation/arena-demo/program-test.c -o
/tmp/arena-program-test` followed by `/tmp/arena-program-test` exercises the
portable guest interpreter. Actual Cortex-M execution requires the existing
Renode test/package route. The mailbox alone never uploads executable bytes.
