# Source-origin review, 2 October 2026

The broader review found no additional uncredited Pybricks implementation in
the reviewed current firmware tree beyond the 46 inventoried source/reference
files. It found provenance and historical-distribution issues. Both current
filter bodies were replaced with credited MIT Fusion adapters, and the approved
public history cleanup now retires the old ancestry and 19 other branch refs.
The recorded blocking findings are resolved within the current-source,
configured-build and advertised-history scope. This does not establish every
possible origin or clear optional external targets and unavailable server objects.

The evidence is recorded in [the review manifest](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/policy/source-origin-review.json).
This is an engineering review of identified sources, not a legal opinion or a
proof that all possible copying has been detected.

## Coverage and method

The firmware source baseline is `8fa6b951980b92e0491a7994a007e35e3cdac617`.
The scan also includes the two audit tools staged during the review. It reads
all tracked text, including host applications, tests, build/configuration files
and documentation, rather than only files already mentioning Pybricks.

| Tree | Revision | Tracked entries | Compared reference |
|---|---|---:|---|
| Firmware plus staged audit tools | `8fa6b95` plus recorded tool hashes | 1,039 | Pybricks `101c6bab` and fetched master `f72fc866` |
| NuttX | `a67efb31` | 25,573 | Pybricks `101c6bab` |
| NuttX Apps | `55f0bc21` | 5,135 | Pybricks `101c6bab` |
| Renode Infrastructure fork | `3055d665` | 1,955 | Pybricks `101c6bab` |

The scanner uses exact lexical sequences with C-style comments and whitespace
omitted, followed by a pass collapsing non-keyword identifiers. It reports
at least 32-token exact sequences or 65-token renamed sequences, seeded by
20-token windows. Seeds occurring more than 80 times in the reference are
ignored. These thresholds are candidate discovery heuristics, not legal
criteria. Comments in other languages remain tokens. Binary entries and
gitlinks are recorded separately; they are not interpreted as source text.

The reviewed matches outside the existing firmware inventory are standard
header sequences, licence text, build separators, shared MicroPython ancestry,
API registration/declaration patterns and protocol constants in separately
pinned Zephyr source. The Renode matches include its already inventoried LPF2
fixture and TLC5955 table; a repeated all-`0xff` test sequence also matches a
TI array but provides no evidence of TI payload import.

The older source-reuse and configured-build inventories remain separate
evidence. A hash pin establishes which bytes were inspected; an inherited
licence label alone does not establish every byte's original authorship.

## Pybricks history clarified

spike-nx introduced its Pybricks submodule in
[`2bcee6b1`](https://github.com/owhinata/spike-nx/commit/2bcee6b1d4e562e89a798b76e66ae0930482bb7f),
pointing at `101c6babb592148bda9a8fd912b7953c7d561c0a`. The submodule history
reachable from the reviewed spike-nx baseline contains one gitlink change.
Every one of the 46 inventoried local paths first appears with that same pin
present. The manifest records the first commit at each current path and its
gitlink; this does not reconstruct authorship of every line or follow every
possible external reading event.

All 46 current files retain the copyright notices of their mapped reference
sources, including The Pybricks Authors, LEGO System A/S and David Lechner.
Their full applicable grants are retained and integrity-checked. The review
also added an explicit [selected UART MIT grant](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/licenses/LEGO-UART-MIT.txt)
with David Lechner's copyright and the upstream relicensing statement.
The Git history now establishes the available reference more precisely than the
earlier wording about unreconstructed extraction history suggested. It cannot
prove that developers consulted only that checkout.

## Findings requiring action

### Inherited Madgwick implementation origin

`host/ImuViewer/src/ImuViewer.Core/Filters/MadgwickFilter.cs` explicitly says
it mirrors a reference C implementation. Its introduction in spike-nx
[`4c90fcbd`](https://github.com/owhinata/spike-nx/commit/4c90fcbd29f0348b8dc36d6a1d6c834336cc3ef3)
also describes it as a C# port. Firmware commit
[`452b7d87`](https://github.com/owhinata/spike-nx/commit/452b7d8757734d49f63bbe9f766903ac220a1038)
explicitly ports that C# filter into `apps/drivebase/drivebase_imu.c`.

The optimized temporary-variable layout and gradient calculation sequence
closely resemble the
[Madgwick reference implementation](https://github.com/arduino-libraries/MadgwickAHRS/blob/9e8ea9c6c85ad4e0d10aee10c24793cd450d46e5/src/MadgwickAHRS.cpp),
whose [distribution declares GPLv3](https://github.com/arduino-libraries/MadgwickAHRS/blob/9e8ea9c6c85ad4e0d10aee10c24793cd450d46e5/README.adoc).
Mathematical equivalence and similarity do not prove copying or establish a
legal conclusion. However, no compatible grant for this specific reference
origin has been established. The inherited root MIT grant is insufficient
evidence to dismiss that concern. The earlier implementations remain unresolved in historical revisions. Both
current paths have now been replaced as described below.

The userspace linker map selects the firmware object and retains its IMU
integration section. This concern therefore also affects the recorded
simulation build, despite that build excluding the TI payload. The earlier
build/licence check verified declared licence selections, input hashes and
notices; it did not establish this implementation's original grant.

### Current filter replacement and validation

Both inherited gradient-descent bodies have been removed from the current tree.
The replacement adapts `HalfGravity`, `Residual` and inclination feedback from
[Fusion at `a8d7224`](https://github.com/xioTechnologies/Fusion/blob/a8d7224f36a0ec82345ef49a3db50e65f8d3bab8/Fusion/FusionAhrs.c),
under its explicit [MIT grant](https://github.com/xioTechnologies/Fusion/blob/a8d7224f36a0ec82345ef49a3db50e65f8d3bab8/LICENSE.md).
Original x-io Technologies copyright and the full grant are retained; local
adaptations are credited. `policy/orientation-filter.json` records the pin,
reference hash, adapted paths, notice hash and behavior changes.

This is acknowledged licensed adaptation, without a clean-room claim. It uses
gravity-vector cross-product feedback and exponential quaternion integration,
rather than the old normalized gradient-descent calculation. It is a reduced
adapter, not a copy of the complete Fusion library: magnetic feedback, startup
and rejection state are omitted. Firmware retains its existing first-sample
attitude seed and stationary gate. Legacy class, state and beta names remain for
caller compatibility; proportional gain is `10 * beta`. Correction dynamics are
changed, and physical hardware tuning is still experimental.

Synthetic C tests cover all three gyro rotation axes in freefall, gravity
convergence from 30 and 150 degree errors, a complete world-yaw rotation at 51
degrees of hub tilt, zero gain and invalid-input handling. All 86 .NET 10 core
tests pass, including the new convergence and input cases. The actual ARM
protected firmware rebuild passes; its input delta consists of the changed
IMU source and the new adapter header. The simulation inventory now records
3,242 conservative inputs, updated image/archive hashes and a byte-identical
replay of the userspace link for its map. TI exclusion passes again. A C/C# replay of 2,000 mixed samples has a maximum
quaternion-component difference of `7.75e-7` (tolerance `5e-5`). The C# project
also copies the Fusion grant into build/publish output.

The current-source finding is resolved within this reviewed build scope.
Older revisions still contain both inherited bodies. A separate historical
finding was resolved for advertised reachability by retiring those revisions
from public refs. Their private archival copies remain uncleared. Merely using the author's
current MIT library does not retroactively relicense the older implementation.

### Historical TI material found in the initial audit

The current tree excludes the service pack. The initial review of 270 reachable
firmware commits and 1,695 blobs found the original TI payload and its
licence, both reachable from all 19 fetched public branch heads, including
main. The original snapshot `5b2bde5` included these files; deleting them in a
later commit did not remove them from history.

This fails the project's exclusively permissive repository-history policy.
It does not by itself establish a breach of TI's licence: the historical
snapshot supplied TI's terms. Current image exclusion and historical source
distribution are different questions.

### Historical notice gaps found in the initial audit

At the initial audit, 17 public feature-branch tips did not contain the current Pybricks/LEGO grant
copies. The corrected main and audit branch have them. Historical snapshots
before the correction must also be considered when distributing Git history
or exporting older branches. The affected refs and hashes are in the manifest.

### Applied public history cleanup

The owner approved the reviewed cleanup. An atomic push with an explicit
expected-tip lease for every ref replaced `main` with new root
`7c7c9bcdf3cab38b4d1794ba3756c97e1fa89da7` and retired the 19 other advertised
branch refs. No tags were advertised. The root's tree exactly equals tested
snapshot `5f2e9fc9572db7b28a05b9a1cd7766824d179c0c`. A fresh clone from GitHub
contained one reachable commit and 1,042 blobs, with zero forbidden-history
findings. The source and configured-build content is preserved unchanged.

All fetched original history is preserved in a verified private local bundle.
Eleven retired branches have commits absent from current `main`; their contents
are archived, without merging their differences or relicensing them. The exact
retired refs, archive digest, root/tree equality and fresh-clone audit are in
[the public history review](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/policy/public-history-review.json).
The archive itself is not part of this distribution.

This resolves the three historical findings for advertised branch/tag
reachability. It does not remove GitHub caches, hidden PR refs, fork-network
objects or other clones, and does not retroactively clear retired source.
The initial GitHub API check listed no firmware releases or Actions artifacts;
that does not prove expired or downloaded material never existed.

### Optional external PHY62xx macros

External NuttX `arch/arm/src/phy62xx/types.h` shares a 206-token exact packing
macro block with TI's BSD-3-Clause `lib/ble5stack/central/hal_defs.h` in the
Pybricks reference. NuttX marks its file Apache-2.0. This may be shared HAL
ancestry rather than Pybricks copying. Its original PHYplus/TI provenance
needs clarification before importing or selecting that input. It is absent
from the recorded STM32 simulation dependency closure. This review does not
clear every optional target in the external NuttX repositories.

## Reproduction and clearance status

`tools/audit_source_similarity.py` accepts two local Git checkouts and produces
hashes and candidate positions without publishing source bodies. Run it for
each tree/reference pair recorded in the manifest. Full raw dependency reports
can be large; the committed record retains their hashes, pins and summaries.
`tools/audit_repository_history.py` checks every reachable blob against the
source policy, including deleted files and aliases. Fetch the intended refs
before running it; it does not inspect unavailable server-only objects.

`tools/check_source_origin_review.py` verifies the review record and affected
current-file hashes. Its `--require-clearance` mode passes for the recorded
resolved findings and still refuses new blocking findings. CI fetches full
history and runs `audit_repository_history.py --require-clean`, which refuses
known forbidden payloads and the retired inherited-filter blob hashes even
when subsequently deleted. These checks do not authorize binary publication
or prove that no unknown copying exists.

The applied cleanup and its branch-preservation consequences are described in
[the history cleanup record](history-cleanup.md).
