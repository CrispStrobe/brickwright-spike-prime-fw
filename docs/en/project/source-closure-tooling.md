<!-- SPDX-License-Identifier: Apache-2.0 -->
# Evidence-backed source-closure tooling

`tools/source_closure.py` prepares review artifacts; it does not copy or vendor
source. A roots JSON file declares each reviewed source root's local path,
repository, immutable commit, permissive licence, build role, and provenance
mode. `git-exact` requires current bytes to equal the declared commit's blob.
A deliberately patched project tree must declare `patched-tree` and a non-empty
`patch_policy`; those entries record the current content hash. Generation
then intersects successful file-consumption evidence from one or more `strace`
logs with compiler depfile prerequisites.

A whole-build trace also observes operating-system executables and libraries,
which are build tools governed by the container boundary rather than firmware
source. Pass it as `--repository-trace`: successful reads beneath
`--repository` join the source closure, while host paths do not. The capture
audit still counts external reads, and the fixed-point gate rebuilds the
materialized tree inside the pinned container with `--network none`. Ordinary
`--strace` remains fail-closed across all paths.

Only MIT, Apache-2.0, and BSD-3-Clause are accepted. An SPDX identifier on a
file overrides its root declaration and is checked independently. Missing
files, paths outside a declared root, escaping symlinks, and unknown or
GPL/AGPL/LGPL/non-commercial expressions fail closed. Failed system calls in a
trace are not evidence that a source was consumed. PID-prefixed `strace -f`
output and unfinished/resumed calls are supported. `--cwd` supplies the first
PID's initial directory; cwd and directory descriptors are inherited by
`clone`/`fork`/`vfork` and updated by successful `chdir`/`fchdir`. Relative
paths and `*at` dirfds resolve from that per-PID state. An uninherited PID or
unknown dirfd fails explicitly. Removed build directories remain valid lexical
cwd evidence because the successful syscall proves they existed.
Nested `LICENSE`/`COPYING` boundaries require an explicit per-path override,
which may also require an SPDX tag.

Example (all output paths are review artifacts, not firmware artifacts):

```sh
python3 tools/source_closure.py generate \
  --roots build/closure-roots.json --cwd "$PWD" \
  --strace build/kernel.strace --strace build/apps.strace \
  --depfile build/kernel.d --depfile build/apps.d \
  --output build/source-closure.json \
  --sbom build/source-closure.spdx.json \
  --map build/firmware.map --object build/kernel.o \
  --evidence build/link-evidence.json

python3 tools/source_closure.py verify \
  --roots build/closure-roots.json --cwd "$PWD" \
  --strace build/kernel.strace --strace build/apps.strace \
  --depfile build/kernel.d --depfile build/apps.d \
  --manifest build/source-closure.json
```

The manifest records root, role, path, SHA-256, licence, and origin repository,
commit, path, and Git blob when available. The SPDX 2.3 JSON has deterministic
ordering and namespace; the optional linkage report hashes maps and objects,
normalizes exact object/archive-member identities, and joins depfile targets
without basename guessing. Ambiguous targets and basename-only map references
fail closed. Verification checks
content hashes and requires exact equality between consumed and manifested
files, catching stale entries and newly consumed, unmanifested files.

## Toolchain and linked-runtime boundary

Project and vendored source admission remains permissive-only. Compiler
executables are build tools, while runtime archives and startup objects selected
by the linker are product inputs. The latter are reviewed separately through
`policy/arm-toolchain.lock.json` and `tools/toolchain_boundary.py`.

The lock names one Arm release archive by HTTPS URL and SHA-256 and records the
exact GCC, newlib, and binutils revisions from Arm's release notes. GCC runtime
and newlib licence evidence is tied to those revisions by URL and content hash.
That is provenance evidence; the verifier never derives a source licence from
strings or machine code in a compiled object.

Licence texts are fetched explicitly from the locked URLs and supplied via
`--license-dir`; their bytes must match the lock before review evidence is
accepted. They are not bundled with the firmware or toolchain.

Linked-runtime evidence uses `brickwright/linked-runtime-evidence/v1`. Each
actually linked file has a path relative to the extracted toolchain, SHA-256,
reviewed component, and the component's exact licence expression. Absolute and
escaping paths, symlink escapes, duplicate files, unknown components, hash
drift, and policy mismatches fail closed. A producer must obtain those exact
paths from the linker command, map, and archive membership, not suffixes.

`tools/link_input_evidence.py` is that producer. Its input declaration maps
each reviewed toolchain-relative file to a component in the lock; it never
infers a component or licence from a basename. It requires the linker's argv as
a JSON string array, its lexical working directory, and every link map. Exact
toolchain paths selected by a map must equal the declarations. For an archive,
the pinned `arm-none-eabi-ar` must find each selected member exactly once; the
report hashes the archive and the bytes of every selected member. Direct
objects are hashed as files. Escapes, missing or stale declarations, unknown
components, ambiguous relative paths, and absent or duplicate members fail.

Example declaration and invocation:

```json
{"schema":"brickwright/runtime-input-declaration/v1","artifacts":[
  {"path":"lib/gcc/arm-none-eabi/13.2.1/thumb/v7e-m+fp/hard/libgcc.a",
   "component":"gcc-runtime"}
]}
```

```sh
python3 -I tools/link_input_evidence.py \
  --toolchain-root /opt/arm-gnu-toolchain-13.2.Rel1-x86_64-arm-none-eabi \
  --declarations build/runtime-inputs.json --link-argv build/link-argv.json \
  --link-cwd "$PWD/nuttx" --map nuttx/nuttx.map \
  --output build/link-input-evidence.json
```

`tools/run_pinned_arm_build.sh` validates the extracted toolchain and runs under
an empty environment with a temporary home, fixed PATH, `PYTHONNOUSERSITE=1`,
and no inherited `PYTHONPATH`, Conda variables, or editable site packages. The
build container uses the same toolchain digest and an immutable Ubuntu image
digest. Its remaining apt packages are not yet locked to an immutable snapshot,
so this checkpoint is the ARM boundary, not a claim of whole-container
reproducibility. Completing S1 still requires producing exact runtime evidence
from a clean build; the boundary deliberately does not guess a selected
multilib.

## Capture requirement

The trace must include descriptor-changing syscalls, because tools such as
`find` duplicate directory descriptors before issuing relative `openat` calls.
Capture a clean build with `%file`, `%process`, and descriptor lifecycle calls:

```sh
strace -f -qq -s 0 \
  -e trace=%file,%process,fcntl,dup,dup2,dup3,close,chdir,fchdir \
  -o build/complete.strace make -j4
```

Enable compiler depfiles for every C, C++, and assembly compilation. Preserve
the link maps, archives, and linked objects until evidence generation finishes.
Run `tools/audit_build_capture.py` before declaring roots; a nonzero result is
a machine-readable blocker and must not be bypassed by guessing a dirfd.
Paths first opened with create, truncate, or exclusive-create flags are proved
generated and excluded from the source set. A `rename(2)` destination inherits
the source's proof and nothing more, because build systems write `X.tmpNNNN`
with a creating flag and rename it onto `X`: the destination is a build product
that was never opened with a creating flag, and an unproved source still leaves
the destination unproved, so a rename cannot launder an undeclared input.
`/dev/fd/N` and `/proc/<pid>/fd/N` are descriptor aliases handed to a child by a
shell process substitution; they are consumption of a descriptor, not of a file.
The audit records stable `$TREE` and `$EXTERNAL` identities for its invocation
and classified paths: the same trace yields a different external count under a
different invocation, but the report never exposes the capture host layout. It
also records connection attempts and fails if any `connect(2)` call succeeds;
endpoints are never serialized.
Its `trace-ready` status applies only to path and network coverage. Final-link
provenance is a separate field and remains `not-evaluated` unless a failed map
and compiler-capture check is recorded explicitly; trace readiness never means
that the capture can generate an accepted closure.

Before tracing, `tools/check_capture_tree_clean.py` must report zero residual
objects, archives, depfiles, maps, or firmware images in every configured
source/build tree. A successful rebuild is insufficient: a stale archive member
can link correctly while having no compiler producer in the capture.
The gate follows internal directory links once, rejects escaping targets, and
permits an `--allow` exception only when the exact path is Git-tracked in its
own repository or submodule.

## Staged upstream sources

`tools/build_zephyr_nuttx_archive.sh` fetches Mbed TLS into a `mktemp`
directory and deletes it on exit, so the capture consumed 263 paths that no
longer existed and that no closure can name. Set `MBEDTLS_SOURCE_DIR` to a
declared root before capturing, and the same build consumes them from a path
the manifest can record:

```sh
tools/fetch_mbedtls.sh /srv/closure/mbedtls-3.6.2      # pins by SHA-256
cd nuttx && MBEDTLS_SOURCE_DIR=/srv/closure/mbedtls-3.6.2 strace -f -qq -s 0 \
  -e trace=%file,%process,fcntl,dup,dup2,dup3,close,chdir,fchdir \
  -o build/complete.strace make
```

Any tool that stages an upstream tree into a temporary directory has the same
defect: the build is honest, the evidence cannot be written. Read-only and read/write paths are
retained; missing or non-file candidates require classification before closure
generation.

## Fixed-point build result

Parallel `make -j8` builds produced identical kernel output but differing user
images and maps because concurrent application archive updates changed member
order. Until archive member collection is canonicalized, the protected build's
reproducibility contract therefore uses serial `make -j1` construction. Two
clean serial builds from the same copied staging tree produced these identical
SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| kernel image | `c5e3d4725852f5f46e923970ec893c55ba5aef9a973e345581f03bb6a38a3bb0` |
| user image | `e5e914a7d59f68be5f193a83b3fdc56a9b1e782a9fcffa1a56ff8cb329ba177e` |
| kernel map | `7622cb6c60ac33039ad479633275aade2ff0fa94446d5fdbccef21f47ea7752c` |
| user symbol listing | `4dcaa5352198a5029ac150bb35455a55752b145c15c2907e58d9ae5ad9c9ee7c` |

This is a measured serial build fixed point, not S1 offline acceptance.
The historical `User.map` artifact in that measurement is output from `nm`, not
a linker map. It proves deterministic symbols but cannot establish archive
member reachability. Protected links now emit `nuttx_user.map` with GNU ld's
`-Map` option; S1 requires a fresh capture using that file.
`policy/firmware-build-inputs.lock.json` now declares the staged LittleFS,
composed Mbed TLS, patched newlib/libm, and Kconfig frontend inputs. Verify their
staged-tree, archive, and patch hashes with `tools/firmware_input_boundary.py`.
The link-input producer expands response files and rejects map outputs or
explicit toolchain artifacts that disagree with the maps. Final manifest, SPDX
SBOM, link evidence, and minimal closure generation still require one capture
that preserves its depfiles and complete linker argv alongside the trace/maps.
