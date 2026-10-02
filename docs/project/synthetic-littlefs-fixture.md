# Synthetic existing-filesystem simulation fixture

The simulator uses an explicit synthetic, already-formatted empty filesystem
for normal-boot scenarios. CI generates it locally and selects those scenarios
by their existing-filesystem tags. The original erased-media first-boot gate
continues to start with erased NOR and loads no fixture. Neither mode uses
production flash contents or modifies a physical hub.

| Robot tag | Initial media and coverage |
| --- | --- |
| `brickwright-board-models`, also `brickwright-erased-first-boot` | Erased NOR; full blank scan, automatic formatting and flash initializer success before the display milestone. |
| `brickwright-existing-filesystem-board` | Explicit generated empty filesystem; existing-filesystem mount and the same flash/display milestones. |
| `brickwright-simulation-hci-existing-filesystem` | Explicit generated empty filesystem; simulation-profile HCI milestones, with the existing TLC5955 display isolation retained. |
| `brickwright-simulation-hci`, also `brickwright-erased-simulation-hci` | Original erased-media simulation HCI scenario; retained for explicit local selection. |

CI selects both the erased and existing-filesystem board scenarios, and the
existing-filesystem simulation HCI scenario. The erased board gate keeps its
15-second guest-time deadline for flash initialization; its 900-second host
deadline accommodates slow simulator execution. Fixture generation and host
tests provide filesystem evidence; guest results are qualified separately.
These scenarios do not qualify physical storage or power-loss behavior.

The generator calls the actual qualified LittleFS v2.5.1 `lfs_format` and
`lfs_mount` implementations, checks that the mounted root contains only `.`
and `..`, and confirms that mount/unmount does not write to the media. Two
independent format/mount runs must produce identical bytes. It accepts only
the recorded hashes of the five external source/licence files; it does not
download or vendor LittleFS or copy any production flash contents. The
original BSD-3-Clause notices remain in those external files. Its host adapter
and tooling are original BSD-3-Clause Brickwright code.

The geometry and persistent limits match the simulation build: a 31 MiB partition beginning at
chip offset 1 MiB, 4096-byte erase blocks, 256-byte NOR pages, LittleFS
read/program/cache sizes of 1024 bytes, 7936 blocks, 200 block cycles and a
992-byte lookahead buffer. Formatting changes only blocks at chip offsets
`0x100000` and `0x101000`. The output contains 8192 bytes of changed blocks,
plus a JSON receipt with geometry, offsets, source hashes and payload hashes.
On a newly created erased model, all other flash bytes remain erased. The reserved first 1 MiB is absent
from the artifact.

Generate only into a new or empty ignored/private directory:

```sh
python3 tools/make_littlefs_fixture.py \
  --littlefs nuttx/fs/littlefs/littlefs \
  --output .local/firmware-images/existing-filesystem
python3 tools/make_littlefs_fixture.py \
  --littlefs nuttx/fs/littlefs/littlefs \
  --output .local/firmware-images/existing-filesystem --check
python3 tools/test_littlefs_fixture.py --littlefs nuttx/fs/littlefs/littlefs
```

The tool refuses to overwrite a populated output directory. `--check` rejects
changed source provenance, geometry, block addresses, payload contents and
coverage claims. The tests also cover source/licence changes, truncation,
corruption, attempted writes into the reserved region, reordered blocks and
output preservation. No generated filesystem data or compiled helper is
committed.

The explicit loader is `tools/renode_load_littlefs_fixture.py`. After platform
creation/reset, while the machine is paused and before the guest starts, the
selected existing-filesystem scenario validates `receipt.json` and
`flash-blocks.bin`, then checks that both destination blocks are erased. It
programs 32 pages of 256 bytes through the existing public NOR SPI interface,
using write-enable and four-byte page-program commands, and verifies both
blocks through four-byte fast-read commands. It never erases or resets the
chip, accesses private model storage, or changes the model's default reset
behavior. A validation failure prevents programming; readback failure stops
the scenario.

The fixture is loaded explicitly on each newly created existing-filesystem
machine. Erased-media scenarios never invoke the loader. The first 1 MiB
reserved area and all bytes outside the two destination blocks are preserved.
Generated data, receipts and compiled helpers stay under ignored `.local/` or
temporary directories and are not published as firmware artifacts.

The host compiler also uses the exact NuttX `fs/littlefs/Make.defs` definitions:
`LFS_NAME_MAX=32`, `LFS_FILE_MAX=2147483647` and `LFS_ATTR_MAX=1022`.
These limits are recorded in the receipt with the geometry and compiler definitions.
The device named `/dev/mtdblock0` is registered with `register_mtddriver`;
NuttX obtains its MTD geometry directly: 256-byte pages and 4096-byte erase
blocks, with the partition reduced to 7936 erase blocks. Read, program and
cache factors of four give 1024 bytes, and automatic lookahead is 992 bytes.

The earlier host-only fixture used LittleFS's default filename limit of 255.
The guest permits 32, so it rejected that fixture's superblock with `-EINVAL`.
The regression now compiles the actual pinned library separately with each
limit: the guest build rejects the old format and mounts the corrected format.
The crash/restart harness uses the same three guest compiler definitions.
