# Storage recovery and NuttX hardening

The SPIKE firmware is experimental. The following targeted fixes retain the
Apache-2.0 and BSD-3-Clause notices in the affected NuttX files, including
the original tickless-driver notices, and the existing MIT notices in the
board driver.

The NuttX descriptor limit correction comes from
[20752312eaac24994487891207c81fa22c02f7b5](https://github.com/apache/nuttx/commit/20752312eaac24994487891207c81fa22c02f7b5)
by AlmAck. The static kernel-group failure cleanup is adapted from
[84f363d79d710780592253e4e08638cb3bcee9c2](https://github.com/apache/nuttx/commit/84f363d79d710780592253e4e08638cb3bcee9c2)
by yushuailong. The task-name buffer correction comes from
[ef37425f71cdaf6c78ef966e05e77939c1f0b78b](https://github.com/apache/nuttx/commit/ef37425f71cdaf6c78ef966e05e77939c1f0b78b)
by Junbo Zheng. Full licence texts and scope are recorded in
[THIRD_PARTY.md](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/THIRD_PARTY.md).

The board flash driver now releases deep power-down before reading JEDEC ID.
This follows the initialization precaution in Michal Lenc's Apache NuttX
[014f22b1c24c02ebf7e53afffdac54b6c96fd8fc](https://github.com/apache/nuttx/commit/014f22b1c24c02ebf7e53afffdac54b6c96fd8fc);
the implementation is a small adaptation for our existing MIT board driver.

On mount failure, automatic formatting requires reading **every byte** of the
31 MB filesystem partition and finding only erased bytes (`0xff`). This can
make the first boot slower. The reserved first 1 MB is never scanned or
formatted by this recovery path. A corrupt, nonblank partition is preserved;
read failures and short reads do not authorize formatting. The partition
remains registered even if its filesystem cannot be mounted.

The scan reads 4096-byte blocks through one bounded kernel-heap allocation,
so the boot task does not need a 4 KB stack buffer. It frees that allocation
on every exit path. Allocation failure returns `-ENOMEM` and does not permit
formatting. A full blank scan makes 7936 read calls instead of 126976; this
reduces transfer setup overhead while still reading and checking every byte.
The simulator's byte-level DMA pacing remains intact, so fewer calls do not
imply the same factor of improvement in elapsed time.

To recover existing data, inspect or back up `/dev/mtdblock0` first. An operator
who chooses to discard the filesystem can explicitly run:

```text
mount -t littlefs -o forceformat /dev/mtdblock0 /mnt/flash
```

This command destroys the filesystem partition, including saved programs.
It is an explicit recovery operation, never the automatic response to
corruption.

Run the host fault-injection tests with:

```sh
python3 tools/test_upstream_hardening.py --nuttx nuttx
```

They compile the changed implementation paths with mocked boundary conditions
and AddressSanitizer/UndefinedBehaviorSanitizer. They cover descriptor limits,
static and dynamic task-group failure cleanup, task-name buffer guards, SPI
wake ordering, blank and nonblank partitions, end-of-partition data, short or
failed reads, allocation failure and cleanup, dirty bytes throughout the
first scan block and across 4 KB/64 KB boundaries, and mount/format errors.

For crash/restart qualification using the actual build's patched LittleFS
v2.5.1 sources, run:

```sh
python3 tools/test_littlefs_power_loss.py nuttx/fs/littlefs/littlefs
```

The test does not download or vendor LittleFS; its existing BSD-3-Clause
copyright and licence remain in the supplied source directory. The runner
prints hashes of the five source/licence inputs. It links the unchanged program
save/restore code through a host POSIX-to-LittleFS shim, uses the simulation
build's 31 MB partition, 256-byte NOR pages, 4096-byte erase blocks and configured
LittleFS cache/transfer sizes, and terminates a separate process at each flash
program, erase or sync operation. Cuts occur before, partway through and after
the operation; partial programming stops midway through a physical page.
Restart discards all process/file/cache state and remounts the persistent bytes.

The qualified-source run passed 426 cuts: maximum-size native and Python
replacement combinations, the same combinations after 64 prior replacements,
and first saves without an existing program. A replacement recovers exactly
the old or new program in READY state; a first save may also recover no file.
Every recovered filesystem accepts another complete replacement. Extracted,
unchanged board mount functions additionally preserve flash byte-for-byte
when both superblock metadata blocks are destroyed or a dirty byte appears
at either partition edge. A wholly erased partition is still formatted.

This models interrupted writes and erase operations; it does not emulate
brownout electrical behavior, arbitrary bit faults, timing, or the complete
NuttX VFS/driver stack. Physical reset/power-loss qualification remains pending.

Use a **clean NuttX build after changing Kconfig**. The broader upstream
[archive rebuild correction](https://github.com/apache/nuttx/commit/c027e7c3e4c803a4bc59ae94eaebba4948ed2514)
is not included in this targeted change; incremental builds can retain stale
archive members after source-selection changes.


## Reproducible init filesystem

The generic `genromfs` tool enumerates host directory entries in filesystem
order. Identical preprocessed init scripts can therefore produce different
ROMFS bytes and generated `etctmp.c` source on a fresh checkout. This breaks
exact source-input verification even when the scripts are unchanged.

The board now selects `tools/make_romfs.py`, an original BSD-3-Clause generator
implemented from the [published ROMFS format](https://docs.kernel.org/filesystems/romfs.html).
It sorts names by encoded bytes, writes explicit `.` and `..` links and
checksums, preserves file bytes and execute bits, and excludes timestamps and
host inode numbers. Device nodes, FIFOs and sockets are rejected. Generic
NuttX boards retain their existing `genromfs` command through the overridable
`GENROMFS` Make variable. The existing C conversion template remains unchanged.

`python3 tools/test_make_romfs.py` verifies creation-order and timestamp
independence, serialized checksums, directory link targets, exact file data,
execute bits, symbolic links, empty files and rejected input types. The actual
preprocessed board init tree was also compared semantically with system
`genromfs` and the resulting image mounted read-only using the Linux kernel
ROMFS driver; script bytes and execute modes matched.

Linux mounting alone did not catch a root-directory layout bug: NuttX starts
its root traversal at the first header and follows sibling links, while Linux
follows the root's directory pointer. An isolated root header made NuttX see
an empty directory and prevented the startup scripts from running. The root
now also links to its directory entries. `python3 tools/test_nuttx_romfs.py
--nuttx nuttx` compiles the actual pinned NuttX parser with directory caching
both enabled and disabled. It reads exact startup-script bytes and tests
nested/sibling paths, long names, empty and missing files; the previous layout
fails both parser configurations. Linux read-only mounting remains valid.

Exact input hashing
remains enabled and the ARM image must be rebuilt for the new deterministic
filesystem layout.
