# Applied repository-history cleanup

The owner approved replacing public `main` ancestry with the exact tested
source snapshot and retiring the other 19 reviewed public branch refs. The
atomic push used a separate explicit expected-tip lease for all 20 refs.
Before publication, the current advertised set exactly matched the reviewed
manifest, including the concurrent program-storage feature branch. No tags
were advertised. The operation succeeded and a fresh clone was checked.

## Evidence and preservation

The new root is `7c7c9bcdf3cab38b4d1794ba3756c97e1fa89da7`; its tree is exactly
that of tested commit `5f2e9fc9572db7b28a05b9a1cd7766824d179c0c`. All source
files, modes, submodule pins and grants were preserved. The fresh published
history had one commit and 1,042 blobs, with zero forbidden-history findings.
The [public history review](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/policy/public-history-review.json)
records the exact retired refs, root/tree equality, archive digest and scan.

All fetched original history is preserved in a verified private local Git
bundle outside the repository. It contains the uncleared historical material
and must not be republished as a permissive distribution. Eleven retired
branches contain commits absent from current `main`; this can include rebased
or squash-merged work. The archive preserves their contents, without merging
their differences into `main`. Any feature brought back from those snapshots
needs source/licence review before publication.

The current source and configured simulation build already use credited MIT
Fusion adapters. Retiring the old ancestry resolves the recorded TI payload,
filter-origin and notice-gap findings for advertised branch/tag reachability.
It does not retroactively license historical revisions.

## Scope and future work

The ancestry change can affect old commit links, clones and pull requests.
It cannot guarantee erasure of GitHub caches, hidden pull-request refs, the
fork network or other people's clones. No global-erasure claim is made.

CI now fetches full history and refuses reviewed forbidden blobs and paths,
including the known retired inherited-filter implementations. Restoring
unreviewed old ancestry or publishing archival branches would reopen the
history findings. Physical hardware remains experimental WIP and has its
separate safety and TI licence requirements.
