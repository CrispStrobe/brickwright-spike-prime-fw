# IMU calibration pipeline

These offline tools convert a valid `IMU_CAP` capture into the calibration file
consumed by the firmware. During the simulation-only phase, generated output is
for fixtures and review; do not install it on a physical hub.

## Data flow

```text
27-byte IMU_CAP frames
  -> bin_to_ascii.py
  -> accel.txt, gyro.txt, meta.txt
  -> run_imu_tk.sh
  -> imu_tk calibration files
  -> imu_tk_output_to_cfg.py
  -> imu_cal.txt
```

## Run

```bash
./bin_to_ascii.py capture.bin --out-dir session_dir
./run_imu_tk.sh session_dir
./imu_tk_output_to_cfg.py --session-dir session_dir
```

`bin_to_ascii.py` rejects sequence gaps and changing full-scale configuration.
`run_imu_tk.sh` runs the pinned calibration container; override its image only
with a reviewed immutable reference. `imu_tk_output_to_cfg.py` requires NumPy
and converts the resulting matrices into the versioned fixed-point schema.

The diagonal calibration scale values should remain close to nominal. Warnings
indicate an invalid or insufficiently varied capture and require a new capture,
not manual editing of the generated file.

Wire definitions are in `apps/btsensor/btsensor_wire.h` and
`apps/btsensor/btsensor_imu_cap_mode.c`. The firmware rejects unknown schema
versions and falls back to identity scale with zero bias.
