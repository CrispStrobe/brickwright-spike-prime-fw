# Licence and provenance inventory

Initial inventory: 2026-09-04 UTC. Source-reuse correction: 2026-10-02 UTC. This is an engineering inventory, not legal advice.
File-level SPDX scanning and review remain mandatory before public release.

The [broader source-origin review](source-origin-review.md) found unresolved
inherited filter provenance, TI material in older reachable commits and missing
corrected grants on older public branch tips. Both current filter bodies have
now been replaced with credited MIT Fusion adapters and the configured firmware
rebuilt. The approved history cleanup now retires the old ancestry and 19
non-main public branch refs. Those recorded findings are resolved for advertised
branch/tag reachability; private archives, server caches and other clones are
not retroactively licensed or erased. Current input/hash checks are scoped
engineering evidence, without a blanket provenance guarantee.

## Policy

Project-owned and vendored source must use permissive licences compatible with
commercial redistribution (MIT, Apache-2.0, BSD-3-Clause, or an approved
equivalent), with no noncommercial condition. MPL/LGPL components are acceptable to the owner
when explicitly inventoried and their distribution requirements are fulfilled;
this firmware correction introduces neither. Generated binaries
must also be checked for linked optional components selected by NuttX
configuration.

The stock CC2564C service pack is an explicitly separated, TI-supplied binary.
TI permits redistribution without modification when its licence is reproduced
and use remains limited to TI devices. A simulation-only repository has no TI
device to serve, so the current tree excludes the service pack: hardware builds
fetch it from TI, and the simulation profile runs without it.
The payload-bearing ancestry has been retired from advertised firmware refs;
the private evidence archive still contains it. CI does not publish flashable firmware while the
hardware-safety gate is open.

## Baseline components

| Component | Baseline provenance | Observed licence | Target disposition |
|---|---|---|---|
| Root `spike-nx` work | `owhinata/spike-nx@00524ea5` | Top-level MIT | Retain after file-level copyright/provenance audit. |
| NuttX fork | `owhinata/nuttx@a67efb31` | Apache-2.0 top level, with optional-component notices | Retain only required build graph; audit fork changes and enabled components. |
| NuttX Apps fork | `owhinata/nuttx-apps@55f0bc21` | Apache-2.0 top level, with optional components | Retain only required build graph; audit selected applications. |
| Pybricks | `pybricks/pybricks-micropython@101c6bab` | MIT only for files carrying its stated MIT SPDX header; dependencies vary | No gitlink remains. 46 adapted/reference files are inventoried in `policy/pybricks-reuse.json`; MIT and LEGO BSD-3-Clause notices are retained. The audited baseline pin is not a claim that every historical extraction used exactly that commit. |
| BTstack | `bluekitchen/btstack@5bc5cbdb` | BSD-like terms plus non-commercial restriction | Forbidden in target; remove in C1.1. |
| CC2564C service pack | `ti-bt/service-packs@3aa1d75f`, byte-exact `TIInit_6.12.26.bts` | TI Text File License; TI-device-only and binary modification/reverse-engineering restrictions | Not distributed. Fetched by the hardware build from TI at the pinned commit with its SHA-256 enforced; source policy forbids it in Git. Generated C containers remain ignored build products. |
| TI licence text | Same TI commit, byte-exact `LICENSE` | TI restricted licence | Fetched with the service pack; source policy forbids it in Git. |
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


## October source-reuse correction

The Pybricks-related application and board files were inherited from
[`owhinata/spike-nx@00524ea5464bddb46c852967e382f8f6b073abe6`](https://github.com/owhinata/spike-nx/commit/00524ea5464bddb46c852967e382f8f6b073abe6).
All 46 inventoried files exist there. Comparing that baseline with our
pre-correction `1715f777f7e5dcd9f780c46e474e4c25a77354fa`, 45 are byte-identical;
`legosensor_uorb.c` adds a non-destructive sensor snapshot interface. The
upstream baseline also contains the Pybricks gitlink at the exact reference
pin below. Per-file comparison results and hashes are recorded in the reuse
manifest. Inheritance does not remove the obligation to preserve notices.

`policy/pybricks-reuse.json` records 46 local files, 28 audited upstream
source/reference files, their hashes, offered licences, selected licences and
original copyrights. UART reuse selects MIT from MIT OR GPL-2.0-only and
retains David Lechner's original attribution. Control-code references include
LEGO BSD-3-Clause notices. Full grants are in `licenses/`. This is acknowledged
reuse; no clean-room or independent-authorship claim is made. The baseline
reference commit was present at all 46 current-path introductions. The broader
review records these first-path commits and the single Pybricks gitlink
introduction in spike-nx. This establishes the available checkout, not every
external source or reading event a developer may have used.

`policy/micropython-embed.json` inventories the MIT embedded interpreter at
v1.26.1, generated configuration outputs and the BSD-3-Clause integer-width
replacement. The cited Stack Overflow formula was removed, not relabelled.
The replacement is copied unchanged from the previously recorded contract-only
component; the record includes its immutable origin and hash.

Source checks verify hashes, licence expressions, attribution and file-set
drift during builds and CI. External NuttX sources, toolchain runtime and
linked image contents are covered for the simulation profile by the configured-build record below. Hardware
images containing the TI service pack have restricted TI terms even though
that payload is absent from Git. The simulation profile excludes it.


## Configured simulation build audit

The default build profile is now `simulation`; `usbnsh` must be selected
explicitly and retains the restricted TI dependency. Hardware approval and
physical validation remain open.

`policy/simulation-firmware-inputs.json` records 3,244 conservative compiler
inputs including headers, generated NuttX interfaces, the complete inventoried
embedded interpreter selection and original linker scripts. Explicit per-file
grants control where available; unmarked project files use their recorded
root grants. Legacy grants and public-domain declarations retain their original
notices. This records declared licence evidence, not reconstructed authorship
of every historical line. NuttX newlib patches and hashes are recorded too.

GNU maps identify 669 kernel and 579 userspace archive-member selections,
plus the directly linked userspace startup object. The userspace link replay
with a map reproduced the ELF byte for byte. Maps include members whose
individual sections can later be discarded, so these are conservative
selection counts, not line or byte attribution. Archive/member hashes and
kernel/userspace image hashes identify the audited build; builds in different
paths can contain different diagnostic strings and need not be byte-identical.

Mbed TLS selects Apache-2.0 from its offered dual licence. GNU libgcc and three
compiler headers explicitly use GPLv3 with GCC Runtime Library Exception 3.1;
20 distinct libgcc members appear across the two images. The exception is
recorded explicitly, with full GPL and exception texts, rather than labelled
MIT/BSD. Newlib libm and toolchain header notices are retained separately.

The full ARM build passed using one job after an earlier build was killed.
Both final binaries contain zero of the 40 TI service-pack fingerprint chunks;
the verbose build references and dependency files contain no service-pack
references, and neither ELF defines the payload symbol.

The full notice bundle is `licenses/Simulation-Firmware-NOTICES.txt`.
Simulation builds run `tools/check_simulation_firmware.sh`, which refuses
unresolved, added, removed or changed compiler inputs; changed configuration
or compiler runtime; changed selected archive/member or direct-object sets;
and missing or altered redistribution notices. Source-only CI checks tracked
project input hashes and the notice bundle. Other profiles, compiler updates
and source changes require review of their own configured build. No binary is
published and simulation-only safety restrictions remain in force.

Simulation configuration is checked before compilation, so a cached hardware
configuration cannot trigger a TI fetch through the default build command.
Shallow/full Git checkouts may yield different literal NuttX version facts;
only those values are normalized for comparison. Added code or changed notices
in that generated header still fail the input check.
