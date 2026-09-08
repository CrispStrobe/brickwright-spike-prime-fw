# Licence and provenance policy

This is an engineering policy, not legal advice. Top-level licences do not
relicense dependencies, generated inputs, or controller firmware.

## Admitted components

| Component | Immutable source | Licence treatment |
| --- | --- | --- |
| spike-nx baseline | `owhinata/spike-nx@00524ea5464bddb46c852967e382f8f6b073abe6` | MIT project baseline; file headers prevail |
| NuttX | `owhinata/nuttx@a67efb31cf4f236e456882589b91862f04594528` | configured Apache-2.0/permissive closure only |
| NuttX Apps | `owhinata/nuttx-apps@55f0bc216565ccab8dee600a88f4485c7693bf8b` | configured Apache-2.0/permissive closure only |
| Zephyr host | commit recorded in `third_party/zephyr-host/manifest.json` | vendored Apache-2.0 selection, byte manifest enforced |
| CC2564C service pack | TI `3aa1d75f3c2ae77f6e4d36194e3d281b899ab149`; SHA-256 `646723c01de351eaf9c6b6b33f4f0dac9567b948a2e93daed9da7a896b6e1b0e` | exact TI-device-only binary and adjacent licence; not project-licensed |
| ARM build toolchain | Arm GNU Toolchain 13.2.Rel1 archive and source revisions in `policy/arm-toolchain.lock.json` | pinned build tools; linked GCC/newlib files require separate exact evidence and notices |

Official LEGO images and packaged Pybricks firmware are user-supplied local
simulation inputs and are not distributed. BTstack is forbidden.

## Import contract

Before importing code, record its repository URL, immutable commit, original
path, copyright, SPDX identifier, local path, modifications, build-graph need,
and licence decision. A copied file is admitted only when its transitive include,
generated-source, archive, and link closure is understood.

Pybricks is not uniformly MIT. Use it and PBIO as behavioral evidence. Reuse a
file only when it carries the required Pybricks MIT header and its complete
closure independently satisfies this policy.

## Build evidence

The release build must derive a deterministic manifest from successful syscall
and compiler-dependency evidence, identify archive membership and linked objects,
and emit SPDX 2.3. It must fail on unknown/compound licences, undeclared inputs,
escaping symlinks, path ambiguity, or hash drift. See
[source-closure-tooling.md](source-closure-tooling.md).

The permissive source validator is not a runtime-library licence validator.
Linked GCC runtime and newlib artifacts remain outside its allowlist and are
admitted only through the separate hash- and provenance-bound toolchain policy.
No compiled object is evidence of its own source licence.

The TI payload is outside this source closure except as an explicit immutable
binary exception. It may be framed and streamed to TI hardware; it may not be
modified, reverse engineered, disassembled, decompiled, or described as
permissively licensed.
