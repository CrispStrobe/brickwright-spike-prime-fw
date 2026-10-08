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
| 1 | Distance 1111; five fixed invalid polls followed by a session poll on one descriptor | EINVAL then four EFAULT refusals, followed by the expected external payload and a nonzero guest session |
| 2 | No new report; session poll | EAGAIN with all 48 sentinel bytes unchanged |
| 3 | Distance 2222; legacy poll, then session poll without a new report | Exact legacy payload, then unchanged empty session poll; one shared queue |
| 4 | Distance 3333; session poll | Exact payload with the original session |
| 5 | Emit distance 4444; detach and advance 500 simulated ms; session poll | Unchanged empty poll after teardown |
| 6 | Attach the same device type; distance 5555; session poll and empty poll | Exact new payload and a strictly greater session; no 4444 payload returned |

A successful session frame is exactly 48 bytes: a nonzero little-endian 64-bit
session, the 36-byte legacy frame and four zero reserved bytes. The legacy frame
is mode 0, length 2, two zero reserved bytes, a little-endian unsigned distance
and thirty zero unused payload bytes. All successes require result/errno zero;
all requests require successful actual open and close. Sensor experiments require
zero observed bridge drive. This is an observation, not a physical safety proof.

The emission budget and 10 ms delivery interval do not independently witness
prior guest-ring residency. Consequently the first batch proves eventual frame
survival through that scenario, not that DATA preceded every invalid call. The
detach experiment proves post-detach absence, not discard of a frame independently
observed in the ring. Synthetic controls have explicit queued frames; their
non-consumption/discard controls cannot be promoted to actual-guest claims.
A later fixture must establish a bounded, read-only admission observation tied to
the exact own-kernel ELF before these stronger claims. It must observe real
admission, without seeding queues or adding a second consuming poll.

Each report must consume exactly one model DATA budget and advance its transmitted
frame count by one, without loss of Streaming or a model timeout. UART delivery
and guest scheduling then advance normally. The fixture must fail if another
consumer, watchdog or resynchronization removes the expected frame; it must not
repair state or reinterpret that failure as non-consumption evidence.

## Controls and execution

```sh
python3 tools/test_lump_request_transport.py
python3 tools/test_lump_active_requests.py
```

The ten existing transport controls remain. Eight new host controls use an
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

Requests have a one-simulated-second bound; synchronization has five seconds and
report emission 200 ms. Host deadlines are checked cooperatively between
synchronous `RunFor` calls and cannot interrupt a stalled call. Robot declares a
600-second test timeout. Timeout does not cancel a mailbox request or authorize
writing reply words; discard handles when resetting the owned machine. This is
not a hard process-supervision or teardown guarantee.

Prior guest-ring admission and invalid-call non-consumption/discard proof,
per-port guest isolation, explicit reset separate from detach/replacement,
cross-reset handle identity, concurrent running programs, atomic conditional PWM,
USB/BLE upload, arena calibration and installed GUI adoption remain open. No
reference image or hardware input is acquired or required by this experiment.
New components use BSD-3-Clause; reused topology notices and retained firmware
attribution remain. No whole-firmware independence claim follows.
