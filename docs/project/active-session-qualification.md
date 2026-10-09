<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Active F DATA qualification

This extends the [qualified inactive mailbox](live-session-mailbox.md) with an
external-input experiment. Host controls and the ordinary protected guest profile
pass at the source recorded below. The complete ordinary/HCI matrix and
seven-peer report audit pass. It changes no firmware C input, configuration or
dependency pin. The inactive
matrix alone does not qualify these new scenarios.

## Observable experiment

Stage the pinned Runtime's compiled electrical topology using
`tools/stage_classic_motor_topology.py`. Preserve its source notices and staging
receipt; do not include source models into the compiled-model Runtime. Load the
fresh ordinary protected firmware pair and explicit synthetic existing-filesystem
fixture. Begin with all six external devices detached, and retain both previous
startup refusal/publication checks before the active experiment.

The only guest memory writes are the four request words in the ELF-resolved
mailbox. Replies, publications, UART queues, synchronization identities, PWM,
registers and function returns remain guest-owned. Device attachment, distance
inputs and DATA budgets use the model's public controls on a paused machine.
The electrical feeder advances with guest simulated time; the fixture never calls
its protocol clock separately or skips guest synchronization.

Attach an ultrasonic model to F and initially permit zero DATA reports. Require
real discovery to reach Streaming with type 62 and mode 0 within five simulated
seconds. Then emit exactly one DATA frame per budget. Distances are synthetic
millimetres, not arena or physical calibration evidence.

| Step | External input and actual guest request | Required observation |
| --- | --- | --- |
| 1 | Distance 1111; five fixed invalid polls followed by a session poll on one descriptor | EINVAL then four EFAULT refusals, followed by the witnessed queued payload and the same nonzero guest session |
| 2 | No new report; session poll | EAGAIN with all 48 sentinel bytes unchanged |
| 3 | Distance 2222; legacy poll, then session poll without a new report | Exact legacy payload, then unchanged empty session poll; one shared queue |
| 4 | Distance 3333; session poll | Exact payload with the original session |
| 5 | Witness admitted distance 4444; detach; wait for an inactive empty ring; session poll | Unchanged empty poll after teardown |
| 6 | Attach the same device type; distance 5555; session poll and empty poll | Exact new payload and a strictly greater session; no 4444 payload returned |

A successful session frame is exactly 48 bytes: a nonzero little-endian 64-bit
session, the 36-byte legacy frame and four zero reserved bytes. The legacy frame
is mode 0, length 2, two zero reserved bytes, a little-endian unsigned distance
and thirty zero unused payload bytes. All successes require result/errno zero;
all requests require successful actual open and close. Sensor experiments require
zero observed bridge drive. This is an observation, not a physical safety proof.

The first candidate [matrix 37805989862](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37805989862)
passed HCI but failed an ordinary active empty-poll assertion. The original error
had no phase detail, so it does not establish which empty poll or teardown cause
failed. Original logs remain preserved. Source-policy and documentation CI passed
that earlier source; it is not an active guest PASS.

This follow-up adds a read-only admission and invalidation witness. The reviewed
collector resolves `g_lump`, `lump_engine_s` and `lump_data_queue_s` from our exact
debug-enabled ARM kernel, checks the array/type/member extents and records its
SHA256 in ignored local metadata. The observer requires that same kernel hash
and loaded ELF symbol, bounded kernel SRAM, the F engine marker, non-overlapping
fields and paused emulation. Metadata offsets rely on the reviewed own-kernel
collector; schema/hash checks alone do not certify arbitrary supplied metadata.
It is diagnostic coupling to our own kernel, not a public guest ABI or a tool for
reference firmware. No new firmware C input or queue mutation is introduced.

Before submitting a request that relies on DATA, the observer must see one active
queued frame with the exact expected bytes, a nonzero session and no drops.
The invalid batch's successful result must carry that witnessed session. Reads
check the header before and after payload access. Head/tail/count must describe
a consistent ring; partial admission, pop or invalidation states are retried by
advancing the real guest, never interpreted as success. After detach the fixture
waits for the actual ring to become inactive and empty, rather than assuming
500 ms is enough for DCM/UART teardown. A missing witness fails before request
submission. Phase and actual-record details now accompany empty-poll failures.
The result records the simulated milliseconds waited for invalidation. These
stronger observations passed in the ordinary guest run recorded below, with
the companion HCI regressions passing in the same complete matrix.

Each report must consume exactly one model DATA budget and advance its transmitted
frame count by one, without loss of Streaming or a model timeout. UART delivery
and guest scheduling then advance normally. The fixture must fail if another
consumer, watchdog or resynchronization removes the expected frame; it must not
repair state or reinterpret that failure as non-consumption evidence.

## Controls and execution

```sh
python3 tools/test_lump_request_transport.py
python3 tools/test_lump_active_requests.py
python3 tools/test_lump_queue_observer.py
```

The ten existing transport controls remain. Nine additional observer/metadata
controls cover exact read extents, paused F ownership, changed/partial headers,
completed invalidation, digest/symbol/layout refusals and missing/conflicting
synthetic DWARF definitions. Nine active-fixture host controls use an
explicit synthetic worker, covering exact scenario order and write capability,
invalid-call consumption, duplicate legacy consumption, identity reuse, corrupted
payload, stale detached DATA, admission, deadlines and loss of synchronization or
unexpected drive. Two mutations of the actual Python comparison code must make
the controls fail assertions: ignored replacement identity and ignored payload.
Setup/compilation errors do not count as detection. These tests do not run the
actual worker, UART, DCM or Renode. Existing compiled request/core mutation checks
remain separate.

The ordinary matrix adds `simulation/renode/lump-active.robot`; HCI skips this
ordinary-only experiment and retains its seven air scenarios. Require both
profiles' complete compiler/linker/notice/resource/TI gates and all applicable
guest checks before adopting a whole-matrix result. Raw receipts remain private.
The completed ordinary profile establishes the finite active experiment below;
the companion HCI profile separately preserves the existing seven air scenarios.

Requests have a one-simulated-second bound; synchronization and observed teardown
have five seconds each. Report emission and subsequent queue admission each have
200 ms. Host deadlines are checked cooperatively between
synchronous `RunFor` calls and cannot interrupt a stalled call. Robot declares a
600-second test timeout. Timeout does not cancel a mailbox request or authorize
writing reply words; discard handles when resetting the owned machine. This is
not a hard process-supervision or teardown guarantee.

Per-port guest isolation, explicit reset separate from detach/replacement,
cross-reset handle identity, concurrent running programs, atomic conditional PWM,
USB/BLE upload, arena calibration and installed GUI adoption remain open. No
reference image or hardware input is acquired or required by this experiment.
New components use BSD-3-Clause; reused topology notices and retained firmware
attribution remain. No whole-firmware independence claim follows.

## Completed protected guest qualification

[Matrix 37816489598](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37816489598)
tests source `d5aa2b45a773917e5c96b02b18538d8c9e562515`, with Runtime
`8f7696aac606d8de90c1a6a0930e48655f03530a` and Infrastructure
`1253d925accca23dfda66d5bca61e78498dcb64f`. The completed ordinary
[job](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37816489598/job/113446339095)
passes all its applicable steps, including actual ARM protected userspace,
inactive mailbox refusals, active F DATA and retained-program restarts. The
companion [HCI job](https://github.com/CrispStrobe/brickwright-spike-prime-fw/actions/runs/37816489598/job/113446339552)
also completed successfully. The strict audit requires exactly two profiles, all
applicable mandatory steps and only the declared profile-specific skips; it passes.

The active fixture passed eight requests using five externally emitted reports.
The first guest session was 1 and the replacement session was 2. Actual queue
invalidation after detach took 790 simulated milliseconds in this run. This
exceeds the earlier fixture's assumed 500 ms delay, but does not identify the
original unlabelled empty-poll failure's phase or cause. Read-only admission,
legacy/session shared consumption, refusal non-consumption, unchanged empty
output, detach invalidation and replacement identity all passed the experiment's
assertions. The Robot test completed in 21.24 wall seconds; this is a single
fixture observation, not a throughput or physical latency guarantee.

The ordinary profile measures 597,900/654,336 bytes of userspace flash and
89,320/98,304 bytes of static RAM, with zero TI payload bytes. Its actual probe
object is 28,236 bytes, SHA256
`d8aad74de697747a89b5692789310669d9cf75357a6992bf8d711648750a8f92`.
These are this build's static measurements, not heap/stack high-water marks.
The HCI profile measures 597,908/654,336 bytes of userspace flash and the same
89,320/98,304 bytes of static RAM, with zero TI payload and the identical probe
object. Both profiles pass compiler, linker, attribution, resource and TI gates.

Seven HCI peer reports pass: direct LE, Scratch Link, IMU acquisition, stationary
readiness, poses, calibration persistence and Classic motors. All identify the
same four firmware files and the exact Runtime above; the motor report uses
the compiled electrical model. The report verifier rejects three negative
controls: a missing report, conflicting image identity and wrong Runtime. These
are verifier controls, separate from the actual comparison-code mutations.

The HCI log also preserves a background `PacedSink._drain`
`ConnectionResetError` traceback after a peer report. The reported peer
assertions and required job steps pass despite that diagnostic; these results
do not qualify helper teardown or prove that background tasks always terminate
cleanly. A separate Runtime helper-lifecycle regression must distinguish expected
connection closure from in-flight delivery failure before closing this gap.

Source-policy and documentation checks also pass at this exact tested source.
Subsequent qualification/handover commits change only Markdown, leaving all
compiled firmware, configuration, dependency, observer and Robot inputs unchanged.
Raw logs, the original failure, report identities and audit receipts are preserved
privately. This qualifies this finite F-only external-input experiment, not the
remaining per-port/program/reset/GUI or physical capabilities listed above.

## Next bounded experiment: two-port isolation

The [fixed E/F follow-up](two-port-isolation.md) now passes its bounded guest
scenario with continued traffic and a separate silence control. The contract
below is historical preparation; arbitrary ports and broader interleavings
remain open. Start with
`tools/lump_request_transport.py`, `tools/lump_queue_observer.py`,
`apps/hubprogram/`, the diagnostic source located by
`tools/check_lump_guest_probe.py`, and `simulation/renode/lump-active.robot`.
Refresh main first and preserve this F-only experiment as a regression.

1. Document two fixed supported port selections in the diagnostic request ABI.
   Preserve its bounded selectors, sequence correlation and descriptor lifecycle;
   do not admit arbitrary guest pointers, addresses or executable input. Extend
   the read-only observer with a validated A–F index and the corresponding actual
   engine port marker. Keep own-kernel hash/symbol/layout validation.
2. Attach two supported external ultrasonic devices on distinct ports. Witness
   one exact frame in each actual guest queue, using different distances. Poll
   one port, require its exact payload, and require that the other queue still
   contains its original payload/session before polling it. Reverse the order
   with new distinguishable reports. An empty or refused poll must not consume
   the other port's report. Do not assume numerical session identities differ
   across ports unless the driver contract explicitly guarantees that.
3. Detach and replace one device while the other stays attached. Witness actual
   invalidation only on the detached port, then require the unaffected port's
   payload and session to survive. Require replacement identity progression only
   within the replaced port. Keep budgets finite and observe zero sensor drive.
4. Add host adversaries for a wrong port marker, swapped replies, cross-port
   consumption and invalidation of the unaffected queue. A mutation of the actual
   comparison must fail an assertion; setup failures do not count. Then run clean
   affected protected profiles and all required guest/air regressions, compiler,
   attribution, resource and TI gates through the existing hosted matrix.

Acceptance requires actual protected-guest payload and identity observations on
both ports, exact source/pins and preserved failures. This two-port slice still
does not establish arbitrary A–F topology coverage, concurrent program readers,
cross-reset identity or atomic motor ownership. Those need separate experiments.
