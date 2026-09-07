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
paths and `*at` dirfds resolve from that per-PID state. An uninherited PID,
unknown dirfd, or unavailable successful directory change fails explicitly.
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
