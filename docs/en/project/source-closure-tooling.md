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
The audit records its own `--cwd` and `--tree` in the report: the same trace
yields a different external count under a different invocation, so counts
without the invocation cannot be reproduced. Read-only and read/write paths are
retained; missing or non-file candidates require classification before closure
generation.
