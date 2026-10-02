# Reviewed NuttX backports

This experimental firmware keeps its existing NuttX and Apps pins, including
F413 support, protected memory layout, persistent RAM reservations and the
zmodem buffer-margin fix. It carries selected newer Apache changes as patches
in `patches/nuttx-hardening/`; this is not a wholesale upgrade to NuttX 13.

[The manifest](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/policy/nuttx-backports.json) records upstream source
commits, authors, adaptation scope, patch hashes and before/after file hashes.
Original ASF headers and NOTICE files remain applicable. The patches retain per-file
[Apache-2.0](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/licenses/Apache-2.0.txt)
and [BSD-3-Clause](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/licenses/NuttX-Tickless-BSD-3-Clause.txt)
grants. The tickless source retains Gregory Nutt and Ansync Labs notices;
local board changes retain the
existing MIT grants and original Pybricks notices.

The build runs `tools/apply_nuttx_backports.py` before configuration. It checks
both exact base revisions and all patch inputs before applying either patch,
accepts an already-applied series, and refuses partial application or source
drift. `--check` requires the reviewed result; `--record-only` verifies patch
and grant hashes without initialized submodules. Reinitializing a dependency
requires reapplying the series. Never replace the dependency pins without
reviewing which existing fork fixes would be lost.

The changes cover:

- USB OTGFS wakeup interrupt delivery after host suspend.
- SPI DMA requests longer than 65,535 words, including automatic continuation
  after the first deferred-trigger chunk.
- Protected syscall number and nesting validation.
- Descriptor-table bounds, task-group failure cleanup and task-name bounds.
- NSH failed output, failed allocations and terminal-mode error handling.
- Tickless compare events missed during setup, zero/subtick delays and
  cancellation across rollover using the full unsigned counter range.
- Deterministic generation of the init-script ROMFS without relaxing source hashes.
- Flash wakeup and [non-destructive mount-failure handling](upstream-storage-hardening.md).

The timer adaptation deliberately avoids upstream's signed remaining-time
calculation: a valid 40,000-tick delay on a 16-bit timer exceeds the signed
half-range. Cancellation uses the hardware compare flag and unsigned modular
subtraction instead. The SPI adaptation starts later chunks automatically;
it preserves the first chunk's deferred-trigger behavior.

Run the focused tests after initializing and patching dependencies:

```sh
python3 tools/apply_nuttx_backports.py
python3 tools/test_nuttx_backports.py
python3 tools/test_make_romfs.py
python3 tools/test_upstream_hardening.py --nuttx nuttx
python3 tools/test_upstream_arm_hardening.py --nuttx nuttx
python3 tools/check_nuttx_apps_hardening.py --apps nuttx-apps --baseline 55f0bc216565ccab8dee600a88f4485c7693bf8b
```

The C regression harnesses compile actual implementation bodies with mocked
hardware and injected failures. The Apps harness rejects the previous faulty
implementations and the old zmodem margin. Its 32,768 worst-case escaping
packets test buffer bounds, not CRC correctness or a complete protocol session.
Target compilation and the existing source/linker/licence/TI gates are separate
checks. Physical USB suspend/resume, DMA operation and interrupted flash writes
remain hardware qualification work; host tests do not establish those results.

Use a clean build after configuration changes. The broad upstream stale-archive
build-system migration remains separate; neither an incremental build nor this
patch series fixes that older build-system behavior.

The timer fix uses STM32 EGR compare-generation bits. Full timer simulation
requires the [companion change in our Renode fork](https://github.com/CrispStrobe/renode-infrastructure-spike-prime/pull/17),
which adds software compare delivery without resetting the counter and checks
masked interrupts and rollover. Twelve register regressions passed on the
combined model. Stock portable Renode 1.16.1 is unchanged; its timer does not
model these compare-generation bits. Startup-only tests on that runtime do not
qualify the new timer behavior.
