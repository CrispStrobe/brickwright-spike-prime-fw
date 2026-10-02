# Optional synthetic LittleFS fixture

This tooling prepares an already-formatted, empty filesystem for a possible
normal-boot simulator fixture. It is an isolated option: no platform, model,
Robot test or release image automatically loads it. It does **not** qualify
booting erased flash, the automatic blank scan, formatting interrupted by
power loss, or physical storage. Those remain separate tests.

The generator calls the actual qualified LittleFS v2.5.1 `lfs_format` and
`lfs_mount` implementations, checks that the mounted root contains only `.`
and `..`, and confirms that mount/unmount does not write to the media. Two
independent format/mount runs must produce identical bytes. It accepts only
the recorded hashes of the five external source/licence files; it does not
download or vendor LittleFS or copy any production flash contents. The
original BSD-3-Clause notices remain in those external files. Its host adapter
and tooling are original BSD-3-Clause Brickwright code.

The geometry matches the simulation build: a 31 MiB partition beginning at
chip offset 1 MiB, 4096-byte erase blocks, 256-byte NOR pages, LittleFS
read/program/cache sizes of 1024 bytes, 7936 blocks, 200 block cycles and a
992-byte lookahead buffer. Formatting changes only blocks at chip offsets
`0x100000` and `0x101000`. The output contains 8192 bytes of changed blocks,
plus a JSON receipt with geometry, offsets, source hashes and payload hashes.
All other flash bytes would remain erased. The reserved first 1 MiB is absent
from the artifact.

Generate only into a new or empty ignored/private directory:

```sh
python3 tools/make_littlefs_fixture.py \
  --littlefs nuttx/fs/littlefs/littlefs \
  --output .local/synthetic-empty-littlefs
python3 tools/make_littlefs_fixture.py \
  --littlefs nuttx/fs/littlefs/littlefs \
  --output .local/synthetic-empty-littlefs --check
python3 tools/test_littlefs_fixture.py --littlefs nuttx/fs/littlefs/littlefs
```

The tool refuses to overwrite a populated output directory. `--check` rejects
changed source provenance, geometry, block addresses, payload contents and
coverage claims. The tests also cover source/licence changes, truncation,
corruption, attempted writes into the reserved region, reordered blocks and
output preservation. No generated filesystem data or compiled helper is
committed.

A future model loader would need an explicit bounded public API, validation
before changing storage, a deliberate reset/load lifecycle, and test coverage
for both this normal-boot fixture and untouched erased-media first boot. This
candidate does not add that integration.
