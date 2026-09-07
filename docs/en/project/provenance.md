# Licence and provenance inventory

Recorded: 2026-09-04 UTC. This is an engineering inventory, not legal advice.
File-level SPDX scanning and review remain mandatory before public release.

## Policy

Project-owned and vendored source must use permissive licences compatible with
commercial redistribution (MIT, Apache-2.0, BSD-3-Clause, or an approved
equivalent), with no GPL-family or noncommercial condition. Generated binaries
must also be checked for linked optional components selected by NuttX
configuration.

The stock CC2564C service pack is an explicitly separated, TI-supplied binary.
TI permits redistribution without modification when its licence is reproduced
and use remains limited to TI devices. The exact allowlisted binary and licence
are therefore carried together, but neither is covered by the project licence.
CI does not publish flashable firmware while the hardware-safety gate is open.

## Baseline components

| Component | Baseline provenance | Observed licence | Target disposition |
|---|---|---|---|
| Root `spike-nx` work | `owhinata/spike-nx@00524ea5` | Top-level MIT | Retain after file-level copyright/provenance audit. |
| NuttX fork | `owhinata/nuttx@a67efb31` | Apache-2.0 top level, with optional-component notices | Retain only required build graph; audit fork changes and enabled components. |
| NuttX Apps fork | `owhinata/nuttx-apps@55f0bc21` | Apache-2.0 top level, with optional components | Retain only required build graph; audit selected applications. |
| Pybricks | `pybricks/pybricks-micropython@101c6bab` | MIT only for files carrying its stated MIT SPDX header; dependencies vary | Reference/provenance input only until each reused file is enumerated. Remove submodule when extraction/audit finishes. |
| BTstack | `bluekitchen/btstack@5bc5cbdb` | BSD-like terms plus non-commercial restriction | Forbidden in target; remove in C1.1. |
| CC2564C service pack | `ti-bt/service-packs@3aa1d75f`, byte-exact `TIInit_6.12.26.bts` | TI Text File License; TI-device-only and binary modification/reverse-engineering restrictions | Retain unmodified beside its licence, with exact hash enforced by source policy. Generated C containers remain ignored build products. |
| TI licence text | Same TI commit, byte-exact `LICENSE` | TI restricted licence | Retain as `third_party/ti-cc2564c/LICENSE.ti`; exact hash enforced. |
| Project planning work | Brickwright commits after upstream baseline | MIT unless a file says otherwise | Retain. |

## Immediate findings

1. The root MIT licence does not relicense submodules or the embedded TI
   payload.
2. BTstack clause 4 restricts redistribution/use/modification to personal,
   non-commercial purposes and therefore fails project policy.
3. The Pybricks top-level licence explicitly says MIT applies only to files with
   the specified MIT SPDX header and warns that bundled dependencies differ.
4. NuttX `NOTICE` describes optional restricted components. Their existence in
   the source tree does not prove they enter this firmware, so the configured
   link graph must be audited.
5. The target defconfig disables `CONFIG_ALLOW_BSD_COMPONENTS`. Permissive
   BSD-3-Clause source can be approved explicitly, but optional dependency code
   is not admitted merely because a build-system switch exists.
6. The TI array is generated from a binary script and the upstream documentation
   says one byte was changed to disable eHCILL. Because the TI licence allows
   binary redistribution only without modification, target code will instead
   preserve an official payload and implement eHCILL in the host transport.
7. Keeping this private history is not permission to publish it later. C7.2
   requires a clean/filtered public history.

## Reuse rules

Before copying or modifying code into the target build, record:

- original repository URL and immutable commit;
- original path;
- copyright and SPDX identifier;
- local destination and whether it was modified;
- why the file is needed in the configured link graph;
- its licence compatibility decision.

Protocol behaviour may be learned from public interfaces, project-owned
extensions, observable traffic obtained lawfully, and permissively licensed
sources. No TI controller payload inspection beyond format validation needed to
stream an official file is allowed.

## CI controls planned for C0.3/C1

- validate submodule URLs and pins against an allowlist;
- scan tracked files and Git diffs for forbidden dependency names and known TI
  payload hashes/patterns;
- run SPDX/license detection with an explicit MIT/Apache allowlist;
- inspect the configured link map, not just repository top-level licences;
- prevent restricted firmware from entering uploaded artifacts or caches;
- use least-privilege workflow permissions and pinned action revisions.
