<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Explicit ultrasonic program readers — bounded guest qualification

Actual E/F native and embedded-Python program readers passed the ordinary
protected ARM guest. The companion HCI profile passed its seven air peers.
This is separate from the diagnostic-only experiments and does not establish
Code-tab, installed GUI or physical support. Existing
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

## Completed evidence

Tested source `f89aa0d9016370f4d9bb82c72e19af9c7dd7b750` passed both clean
protected profiles in [matrix37909305186](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37909305186).
Exact-source [CI37909237011](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37909237011)
passed both enabled checks on GitHub's synthetic merge `41d3c193a9caf806aaf2d9877b902702ab990742`;
its tree equals the tested source tree. Runtime remains
`b34becc947ac9c998881bb018dfe2cec4b1398b2`; Infrastructure remains
`1253d925accca23dfda66d5bca61e78498dcb64f`.

Hosted `tools/check_hubprogram.sh` compiled actual device, interpreter, service
and embedded-Python controls. They cover encoded port boundaries, native
polarity/unknown values, legacy behavior, wrong mode/type/length, unchanged
error output, repeated caught ESTALE, mixed legacy/explicit reads and restart
recovery. All eight actual C-source mutants failed assertions in their intended
control functions: session, sticky failure, port, type, lifecycle, polarity,
unknown handling and conditional direction. Compilation/setup failure does
not count as detection. No compiler or emulator ran locally.

`simulation/renode/program-sensors.robot` uploads through the actual service
mailbox, supplies finite external E/F UART reports and uses an exact-ELF,
read-only queue observer. Only declared program request fields are written in
guest memory. Startup refusals finish before program reads; no competing direct
reader or class mode writer is introduced. The actual program cases passed:

- Native E-below/F-above conditions consume distinct admitted reports.
- Unknown distance cannot satisfy a native wait; STOP cancels it.
- Embedded Python returns exact E/F millimetres, including unknown-1.
- Synchronized empty queues produce EAGAIN; sessions stay active and unchanged.
- A synchronized color device produces ENODEV and keeps its identity.
- Six E conditional trials distinguish below/above, equality and unknown by
  consumed DATA and the actual branch PC.
- Native same-payload F replacement fails ESTALE; retained START without upload
  clears the binding and consumes another report normally.
- Embedded Python catches ESTALE, refuses three subsequent reads, then faults
  with the expected errno. Release and a new program recover E/F reads.

The guest emitted18 reports and205 mailbox requests in24660 simulated
milliseconds. Native F session5 became6; Python F session7 became8. Values and
errno comparisons are exact. The external report cap is24 and the fixture bound
is60 guest seconds after startup; each transmission/admission/consumption has
a200-ms bound using20-ms guest steps. Upload occurs with external inputs detached;
attachment follows upload so DATA silence during upload cannot masquerade as
reader failure. No motor drive was observed at paused checkpoints.

Both profiles measured598412/654336 bytes of userspace flash and89376/98304
bytes of static RAM, with zero TI payload. Both measured the unchanged28480-byte
probe object with SHA256
`3cf60b9d3b4fe920ed63da5af6f5147e5d8a5202a884f1e6015b9a09609a6475`.
The ordinary profile completed retained guest/storage regressions and both E/F
diagnostic role orders. HCI intentionally skips these ordinary-only fixtures
and completed seven separate air peers. Existing inventory image/archive hashes
remain historical; this qualification does not claim reproducible whole binaries
or blanket licence clearance.

## Preserved failures and limits

The first host attempt failed on a misleading-indentation warning in its reset
fixture; compiler warnings and assertions were retained when fixing it.
The first actual program fixture in
[matrix37906760086](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37906760086)
failed before sensor completion with a monitor paused-state binding error.
The revision explicitly binds observer callbacks outside its comprehension,
captures the hub instance and preserves Python tracebacks on failure. The retry
passed; this does not uniquely identify the original runtime cause. Original
failures, raw logs and review records remain private. Read-only licensed
integration review is not an independence claim.

A–D addressing and malformed-frame behavior have host controls only. Native
conditional guest trials cover E; replacement and repeated caught-ESTALE guest
trials cover F. Concurrent mode writers/readers, physical sample age, cross-reset
identity, additional sensor kinds and physical behavior remain open. No result
above implies arbitrary A–F guest equivalence.

Next, explicitly adopt this qualified firmware in Brickwright Lite and exercise
installed Code-tab/shared-arena paths with capability-gated selectors. Keep older
firmware's legacy compiler behavior and refuse unsupported addressed reads.
Consumer pins and current UI advertisement are unchanged by this firmware lane.
