# Classic recovery and cold calibration

The [source-bound receipt](qualification-2026-10-28.json) records source-built
TI-free HCI firmware and the independently compiled Linux Runtime. No firmware
application code changed for these tests. Host controls cover the harness;
the following results execute the actual protected ARM guest.

- Classic signed and concurrent jobs, cancellation/replacement, loaded timeout
  and explicit unsupported/invalid requests passed with actual bridge/encoder
  observations.
- `--motor-case disconnect` starts an unfinished 10,000-degree job, actually
  disconnects its authenticated transport without STOP, observes bridge release,
  then authenticates a new connection. Release took 10,500 guest microseconds;
  the replacement's requested -180 degrees produced -182.903 degrees. Quiet
  windows reject stale replies before and after replacement.
- The separate electrical detach case observes the guest device type change
  from motor to NONE and its event counter advance. Release took 789,989 guest
  microseconds. Reattachment advances the counter again and a fresh -90-degree
  job produces -94.752 degrees. This covers the selected sequence rather than
  arbitrary hotplug interleavings.
- Calibration learns through sequence 441, SAVE succeeds, and same-process
  STOP/LOAD/reopen preserves bias without preserving readiness. A paused monitor
  exports the model's complete 32 MiB NOR medium. A fresh emulator process
  restores those exact bytes before loading the same source-built image pair.
  Its first actual sample has the saved zero-corrected gyro and upright gravity,
  while readiness remains false. Image and medium digests must match; missing,
  malformed, oversized, changed or mismatched custody receipts are refused.

The original paired-IMU/NOR fixture passed cold SAVE and restore. The optional
`--imu-topology` repeats this qualification using the compiled TLC5955 and its
analytical TIM12 clock at the board's full 96 MHz source rate. Stage it with:

```sh
python3 tools/stage_imu_calibration_topology.py --runtime "$RUNTIME_SOURCE" --output "$TOPOLOGY"
```

Use separate new work directories for the two Classic calibration invocations:
`--imu-flash-output "$MEDIUM"` for SAVE, then `--imu-cold-restore "$MEDIUM"`
for restore, both with `--classic --skip-le --imu-calibration`, the same own
`--images`, validated synthetic `--existing-filesystem`, and compiled `--renode`.
Add `--imu-topology "$TOPOLOGY"` to use the aggregate-clock fixture. No new output
may overwrite earlier media or evidence.

The first aggregate-clock attempt failed because the harness's two-second host
poll observed the finite feeder after the guest's 300 ms snapshot freshness
limit. Its failure remains retained. Polling now observes feeder completion
promptly; the successor passed both phases with exact sequences 1, 101, 261,
441, 1 and a distinct first sample after cold restore. Guest freshness,
sample counts, readiness and timeouts are unchanged.

These results qualify synthetic emulator media and selected connection
sequences. They do not establish physical brownout durability, analog motor
accuracy, HOLD behavior, counter wrap or timer-rearm failure recovery.
