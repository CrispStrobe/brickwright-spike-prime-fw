<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Explicit ultrasonic program readers — candidate

This candidate has hosted compiler controls but remains unqualified for merge.
It is separate from the E/F diagnostic
and does not establish Code-tab, installed GUI or physical support. Existing
sensor selectors1–6 keep their fixed C/D/E behavior. The instruction layout and
sensor callback ABI are unchanged.

## Additive interface

Native wait/conditional opcodes3/5 accept `0x100 + (port << 3) + predicate`,
where port0–5 means A–F and predicate1/2 means distance below/above a threshold
in0–65535 millimetres. Valid tokens are0x101/102 through0x129/12a; every other
encoding is rejected. Unknown distance-1 satisfies neither comparison.
The legacy selectors retain their original encoding and behavior.

Embedded Python adds positional `brickwright.sensor(selector, port)` for
selector1/2 only, plus C–F constants; A/B remain0/1. The one-argument form
continues to accept only legacy selectors1–6. Arguments use the existing
bounded MicroPython integer conversion: booleans follow its integer semantics;
negative/out-of-range values fail before unsigned conversion, and overflowing
integer conversion remains an explicit error. Keyword arguments are not added.
A successful read returns signed millimetres, including-1 for unknown.

## Session, consumption and lifecycle

The explicit reader uses `/dev/legoportN`, type62/mode0 and the existing
session-bearing destructive poll. It never returns a legacy cached sample.
Only a successful valid frame binds the reader's first nonzero synchronization
session. This binding is separate from legacy cache/motor state. Later differing
nonzero sessions latch ESTALE before payload validation, even if the replacement
payload is identical or malformed. A caught ESTALE remains latched on further
reads, without polling or publishing output. Only program release/restart clears
it. Legacy calls cannot clear the explicit binding.

Errors preserve the output value: EINVAL for invalid selector/null output or
service reads outside RUNNING; EAGAIN for missing synchronization/empty DATA;
ENODEV for wrong type; EPROTO for zero session, wrong mode or malformed length;
ESTALE for a changed bound session. Other syscall errors propagate, including
EBUSY for a competing direct port opener. No sensor read applies PWM. The service
checks RUNNING before dispatch and prevents calls through a missing callback.

A newly consumed frame has no driver receive timestamp. This does not prove a
physical age or100-ms acquisition freshness. Sessions identify completed
synchronizations during one boot; they are not atomic connection tokens,
cross-reset identities or motor ownership. The class sampler uses callback-backed
class data rather than this destructive ring, but it can select modes and bind a
class to a lower port. Concurrent class/direct mode writers remain outside this
slice; first guest fixtures must declare their reader/mode ownership explicitly.

## Retained interpreter integration

The retained MIT MicroPython qstr table needs C–F names for the added constants.
`tools/update_micropython_port_qstrs.py --check` verifies a reproducible four-row
extension, preserves every original generated row/static ABI pool and keeps the
remaining constant pool sorted. The BSD-3-Clause updater and retained MIT table
have distinct attribution; exact table/compiler-input hashes and modification
records are updated. This does not claim the retained interpreter is newly
independently authored. The header is retained in source; no network build step
is added.

## Required evidence

Hosted `tools/check_hubprogram.sh` must compile actual device, interpreter,
service and embedded-Python controls. New controls cover all encoded port
boundaries, native polarity/unknown values, preserved legacy behavior, wrong
mode/type/length, unchanged error output, repeated caught ESTALE, mixed
legacy/explicit reads and restart recovery. Five actual C-source mutants must
fail assertions in the intended new control functions; compilation/setup failure
is not detection. These controls and all five assertion-detected C-source
mutants passed hosted
[CI37903744205](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37903744205)
on source `0a046f7315c0f1d851ef0307d2f568b9955eaa5d`. The preceding CI failed
on a misleading-indentation warning in the host fixture reset loop; its fix
retained compiler warnings and assertions. No compiler ran locally.

The separate `simulation/renode/program-sensors.robot` candidate uses the real
ARM service mailbox, external UART E/F reports and an exact-ELF read-only queue
observer. Its native cases cover opposite polarities, unknown wait/cancellation,
identical-payload replacement rejection and retained START recovery. Embedded
Python cases cover exact E/F values, unknown, missing DATA, three caught stale
reads and recovery after release. Uploads occur with external inputs detached;
fresh attachment follows upload to avoid exhausting the DATA silence interval.
The report cap is24, execution bound60 guest seconds after startup, and each
transmission/admission/consumption has a200-ms bound. Only program mailbox
request fields are written in guest memory. These are proposed assertions,
not guest results. Wrong-type and additional conditional cases still need
actual guest coverage before merge.

Before merge, bind changed compiler inputs and licence notices, perform source
review and clean both protected builds, all applicable guest/air regressions,
resource/linker/compiler/TI gates and exact-head CI. Actual native and embedded
Python E/F reads, unavailable/wrong-type errors and replacement rejection need a
separate ARM fixture. Do not infer this from diagnostic-only E/F coverage.
Then explicitly adopt the qualified firmware in Brickwright Lite and exercise
installed Code-tab/shared-arena paths. Other A–F ports remain host-only until
actual per-port guest evidence exists. No current UI advertisement is changed.
