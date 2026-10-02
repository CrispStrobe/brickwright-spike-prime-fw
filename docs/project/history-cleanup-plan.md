# Proposed repository-history cleanup

The current source and recorded simulation build use the credited MIT Fusion
adapters. Public ancestry still exposes the inherited filter bodies, the old
TI payload, and older branch tips without the corrected grant copies. A normal
commit cannot remove material from reachable history.

The locally prepared option is to start `main` at a new root commit with
**exactly the tested current source tree**, and retire the other advertised public branch refs listed in the preservation manifest.
There are currently no advertised tags. A new program-storage feature branch
appeared during this work, so the ref set must be refreshed before publication. This is a proposal;
no ancestry replacement or branch deletion has been published.

## Preservation and consequences

All fetched history is preserved in a verified local Git bundle outside the
repository. That private archive contains the uncleared historical material
and must not be republished as a permissive distribution. A manifest records
each advertised ref and its exact tip, the bundle hash, the proposed root
commit and tree, and the draft history scan.

Multiple non-main branches have commits that are not reachable from current
`main`; the manifest records the exact counts, including new branches created
while this audit is running.
This may include rebased or squash-merged work; commit counts alone do not prove
that their functionality is absent. Their contents are preserved in the local
bundle. Retiring those refs would remove their branch names from GitHub, without
merging their differences into `main`. Any features brought back from those
snapshots need an explicit source/licence review before publication.

The new root preserves every file, mode, submodule pin and source notice in the
tested current tree. It does not preserve public commit ancestry. Commit links,
existing clones and open pull requests can be affected. The origin review
continues to report the historical findings until the public refs are changed
and checked again.

## Review before publication

Check the candidate tree equals the tested source tree, the local archive
verifies, the draft reachable-history scan finds no forbidden payload, and the
old filter bodies are absent from candidate source. Review the exact ref list
and the unmerged-commit counts in the local manifest. Publication requires
explicit approval of the ancestry replacement and branch retirement because
those actions change published history and remove branch names.

Use an atomic push with a separate explicit expected-tip lease for every ref;
abort if any advertised ref has changed or appeared since preparation. Do not
use an unconditional force-push or a mirror push. Preserve the private archive
and the preparation manifest. After publication, fetch and recheck every
advertised branch/tag and update the origin review with the resulting evidence.

Changing advertised refs cannot guarantee deletion of old objects from GitHub
caches, hidden pull-request refs, the fork network or other people's clones.
Those limits must remain explicit; no claim of global erasure is justified.
