<!-- SPDX-License-Identifier: BSD-3-Clause -->
<!-- Copyright (c) 2026 Brickwright contributors -->

# Active F DATA qualification candidate

This extends the [qualified inactive mailbox](live-session-mailbox.md) with an
external-input experiment. Host controls pass; actual active guest qualification
is pending. It changes no firmware C input, configuration or dependency pin.
The inactive matrix does not qualify these new scenarios.

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
stronger observations remain candidates until a fresh guest matrix passes.

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
guest checks before adopting a result. Raw receipts remain private. No actual
active PASS is claimed until that run completes and its exact inputs are audited.

Requests have a one-simulated-second bound; synchronization and observed teardown
have five seconds each. Report emission and subsequent queue admission each have
200 ms. Host deadlines are checked cooperatively between
synchronous `RunFor` calls and cannot interrupt a stalled call. Robot declares a
600-second test timeout. Timeout does not cancel a mailbox request or authorize
writing reply words; discard handles when resetting the owned machine. This is
not a hard process-supervision or teardown guarantee.

Actual qualification of the new guest-ring witness and its stronger proof,
per-port guest isolation, explicit reset separate from detach/replacement,
cross-reset handle identity, concurrent running programs, atomic conditional PWM,
USB/BLE upload, arena calibration and installed GUI adoption remain open. No
reference image or hardware input is acquired or required by this experiment.
New components use BSD-3-Clause; reused topology notices and retained firmware
attribution remain. No whole-firmware independence claim follows.
