# External build inputs, measured

S1 step 2 cannot declare roots, pins and licence overrides without knowing what
the protected build consumed from OUTSIDE the tree. Nobody had listed those
paths. This is the measurement, not a declaration: nothing here is pinned,
allowed, or overridden.

Reproduce it with the recorded invocation:

```sh
tools/external_inputs.py \
  --trace /tmp/brickwright-nuttx-recapture.trace \
  --cwd   <capture root>/nuttx \
  --root  <capture root> \
  --out   evidence/source-closure/external-inputs.json
```

The committed report is `evidence/source-closure/external-inputs.json`. Counts
without their invocation cannot be reproduced, so the file records which mode
produced it and against which root.

## The split

`trace_paths` on the descriptor-complete recapture reports **6550 consumed, 263
missing, 6287 existing** — the figures in `recapture-audit.json`, reproduced.
Of the 6287 that exist:

| bucket | paths |
|---|---|
| inside the capture tree | 5403 |
| the source checkout the capture was made from | 497 |
| **external** | **387** |

## What owns the 387

265 are owned by 78 Debian packages; **122 are owned by nothing**. The largest
owners are `cmake-data` 94, `gcc-arm-none-eabi` 21, `coreutils` 20,
`binutils-arm-none-eabi` 15, `libnewlib-dev` 14, `libc-bin` 13, `libc6` 8,
`libnewlib-arm-none-eabi` 3, and a tail of seventy packages with one or two
files each.

**Only 30 of the 387 flow into the image.** A path whose name ends in a header,
archive, object, linker script or specs suffix is compiled or linked in and its
licence flows into the product; everything else is a tool, a tool's shared
library, or a runtime read. The 30 come from four packages, and are listed
per package in the report.

## The 122 with no package

| what | paths |
|---|---|
| a miniconda Python under `/opt/miniconda` and `/mnt/volume1/miniconda` | 94 |
| the invoking user's own `~/.local/lib/python3.13/site-packages` | 14 |
| runtime reads, not inputs (`/dev/urandom`, `/proc/*`, `/etc/{passwd,group,hosts,resolv.conf,nsswitch.conf,ld.so.cache}`, the CA bundle, the locale archive) | 14 |

None of the 122 is a header or a link input, so by the test above **nothing
they produced is in the image** and they are outside S1's licence scope. They
are an S2 problem instead: S2 requires every tool pinned by immutable digest,
and this build ran under an unpinned interpreter from `/opt` plus the invoking
user's site-packages — including three `__editable__` installs that point at
unrelated projects on the same machine
(`__editable__.catfish_search-1.1.0.pth`, `__editable__.crispasr-0.8.8.pth`,
`__editable__.crisptts-0.3.0.pth`). An editable install reaching out of the
build tree is the sharpest available evidence that the tool environment is not
pinned: the build depends on directories that no manifest names and that nobody
else has.

## Finding: the licence of what is LINKED cannot be read from this machine

Four packages supply the 30 files that flow into the image, and the metadata is
weakest exactly where it matters:

| package | files that flow in | what `/usr/share/doc/<pkg>/copyright` says |
|---|---|---|
| `libnewlib-dev` | 14 newlib headers (`reent.h`, `sys/config.h`, `fenv.h`, …) | prose from 2004, no DEP-5 `License:` field |
| `gcc-arm-none-eabi` | 12 — `libgcc.a`, `crtbegin.o`, `crtend.o`, `crti.o`, `crtn.o`, `float.h`, `stdarg.h`, `stdatomic.h` | one line: `Copyright: GNU General Public License` |
| `libnewlib-arm-none-eabi` | 3 — `crt0.o` ×2 and `libc.a` | prose from 2004, no DEP-5 `License:` field |
| `cmake-data` | 1 — `CMakeCompilerABI.h`, a compile probe | proper DEP-5: BSD-3-clause, Apache-2.0, Expat, … |

Upstream, both are fine: GCC's runtime objects and `libgcc` carry the GCC
Runtime Library Exception, and newlib is BSD-family. **Neither fact is recorded
anywhere on this machine.** `ALLOWED_LICENSES` in `tools/source_closure.py` is
`{Apache-2.0, BSD-3-Clause, MIT}` and `FORBIDDEN_LICENSE` refuses any expression
matching GPL, LGPL or AGPL outright, so the closure cannot satisfy its own rule
from package metadata for the files that are actually linked into the firmware —
it would read "GPL" for the package supplying `libgcc.a` and the C runtime
startup objects, and nothing parseable for the one supplying `libc.a`.

Two ways to close it, for the maintainer to choose between:

1. Declare those files under their upstream terms with a cited source — the
   exception text in the GCC sources, `COPYING.NEWLIB` in newlib — so the
   override names the evidence rather than asserting a licence.
2. Widen the allowed set to name the Runtime Library Exception explicitly.

This document does neither.

## Method: three rules, each of which decides a number

1. **The tree is the capture root, not the build's working directory.** The root
   holds about twenty-five entries, so taking `nuttx/` as the boundary makes every
   sibling — `apps/`, `bluetooth/`, `third_party/` — read as an external dependency.
2. **Membership is decided on resolved paths.** The build ran under a `/tmp`
   symlink to the offload volume, so a string comparison against the offload path
   puts 1875 in-tree sources outside the tree, including the project's own
   Bluetooth daemon.
3. **Ownership resolves one symlink hop at a time.** A fully resolved path can
   leave the package's namespace: `/usr/lib/arm-none-eabi` is a symlink to
   `/mnt/volume1/opt/arm-none-eabi` (the root disk was freed on 2026-09-07) and
   `/usr/lib/arm-none-eabi/lib` is a Debian alternatives link, so `realpath()`
   lands on a path dpkg has never heard of while the intermediate hop is owned.
   Resolving to the end reports `crt0.o` and `libc.a` — objects linked into the
   firmware — as having no provenance at all, when `libnewlib-arm-none-eabi` owns
   them two symlinks away. Six of the 387 are findable only this way, and the
   report records the hop each was found at.
