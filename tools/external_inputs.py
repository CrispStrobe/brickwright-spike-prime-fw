#!/usr/bin/env python3
"""Every EXTERNAL existing path the protected build consumed, with its provenance.

S1 step 1 classified what the build read from inside the tree.  This answers the
question step 2 cannot declare roots without: of the paths that EXIST and are
NOT part of the tree, which package owns each, under what licence, and which are
owned by nothing at all.

Method, and each clause of it was a mistake first:

  * The tree is the CAPTURE ROOT, not the build's working directory.  The root
    holds ~25 entries (apps, boards, bluetooth, nuttx, nuttx-apps, third_party,
    tools, ...); taking `nuttx/` as the boundary calls every sibling external.
  * Membership is decided on RESOLVED paths.  The traced build ran under
    /tmp/brickwright-closure-recapture.<id>, a symlink to the offload volume, so
    a string comparison against the offload path misses 1875 in-tree sources.
  * The checkout the capture was made FROM is its own bucket.  It is first-party
    but outside the tree, and folding it into "external" overstates the problem.
  * Ownership resolves ONE SYMLINK HOP AT A TIME.  A fully resolved path can
    leave the package's namespace entirely: /usr/lib/arm-none-eabi is a symlink
    to /mnt/volume1/opt/arm-none-eabi on this machine (the root disk was freed
    on 2026-09-07), and /usr/lib/arm-none-eabi/lib is a Debian alternatives
    link, so realpath() lands on a path dpkg has never heard of while the
    intermediate hop is owned by libnewlib-arm-none-eabi.  Ask dpkg at every hop.

  tools/external_inputs.py --trace <file> --cwd <dir> --root <dir> --out <json>
  tools/external_inputs.py --paths <file> --root <dir> --out <json>

`--paths` takes an existing list of external paths and skips the trace parse,
which needs the whole 343 MB stream in memory; the output records which mode
produced it.  Nothing here declares anything: it reports.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DPKG_INFO = Path('/var/lib/dpkg/info')
DOC = Path('/usr/share/doc')
# A path that ends in one of these is COMPILED OR LINKED INTO the image, so its
# licence flows into the product.  Everything else is a tool, a tool's shared
# library, or a runtime read.
FLOWS_IN = ('.h', '.hpp', '.inc', '.a', '.o', '.ld', '.specs')
LICENSE_FIELD = re.compile(r'^License:\s*(.+?)\s*$', re.M)


def dpkg_index() -> dict[str, str]:
    owner: dict[str, str] = {}
    for listing in DPKG_INFO.glob('*.list'):
        package = listing.name[:-5].split(':')[0]
        try:
            text = listing.read_text(errors='replace')
        except OSError:
            continue
        for line in text.split('\n'):
            if line:
                owner.setdefault(line, package)
    return owner


def hops(path: str) -> list[str]:
    """Every form of `path`, resolving the longest symlinked prefix one hop at a time."""
    seen = [path]
    current = path
    for _ in range(12):
        parts = Path(current).parts
        following = None
        for index in range(len(parts), 0, -1):
            prefix = str(Path(*parts[:index]))
            if os.path.islink(prefix):
                target = os.path.normpath(
                    os.path.join(os.path.dirname(prefix), os.readlink(prefix)))
                following = os.path.normpath(os.path.join(target, *parts[index:]))
                break
        if following is None or following == current:
            break
        current = following
        seen.append(current)
    return seen


def owner_of(path: str, owner: dict[str, str]) -> tuple[str | None, str | None]:
    for form in hops(path):
        # Debian's merged-/usr means a file installed as /lib/x is read as /usr/lib/x.
        for candidate in (form, form[4:] if form.startswith('/usr/') else '/usr' + form):
            if candidate in owner:
                return owner[candidate], form
    return None, None


def licence_of(package: str) -> dict:
    copyright_file = DOC / package / 'copyright'
    if not copyright_file.exists():
        return {'machine_readable': False, 'fields': [], 'note': 'no copyright file'}
    text = copyright_file.read_text(errors='replace')
    fields: list[str] = []
    for match in LICENSE_FIELD.finditer(text):
        value = match.group(1)
        if value and value not in fields:
            fields.append(value)
    if fields:
        return {'machine_readable': True, 'fields': fields}
    # Not DEP-5.  Report that fact rather than guessing a licence from prose.
    return {'machine_readable': False, 'fields': [],
            'note': 'copyright file is prose, not DEP-5; no License: field to read'}


def split(paths: list[str], root: Path, checkout: Path) -> dict[str, list[str]]:
    real_root = os.path.realpath(str(root))
    buckets: dict[str, list[str]] = {'tree': [], 'checkout': [], 'external': []}
    for path in paths:
        resolved = os.path.realpath(path)
        if resolved == real_root or resolved.startswith(real_root + '/'):
            buckets['tree'].append(path)
        elif resolved.startswith(str(checkout) + '/') or path.startswith(str(checkout) + '/'):
            buckets['checkout'].append(path)
        else:
            buckets['external'].append(path)
    return buckets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace')
    parser.add_argument('--cwd')
    parser.add_argument('--paths')
    parser.add_argument('--root', required=True)
    parser.add_argument('--checkout', default='/mnt/volume1/code/lego')
    parser.add_argument('--out', required=True)
    arguments = parser.parse_args()

    root = Path(arguments.root)
    if arguments.trace:
        import source_closure as sc
        consumed = sc.trace_paths(Path(arguments.trace), Path(arguments.cwd))
        existing = sorted(str(p) for p in consumed if p.exists())
        source = {'mode': 'trace', 'trace': arguments.trace, 'initial_cwd': arguments.cwd,
                  'consumed': len(consumed), 'existing': len(existing),
                  'missing': len(consumed) - len(existing)}
        buckets = split(existing, root, Path(arguments.checkout))
        external = buckets['external']
        counts = {k: len(v) for k, v in buckets.items()}
    elif arguments.paths:
        external = [l for l in Path(arguments.paths).read_text().split('\n') if l.strip()]
        source = {'mode': 'paths', 'paths': arguments.paths}
        counts = {'external': len(external)}
    else:
        parser.error('one of --trace or --paths is required')

    owner = dpkg_index()
    by_package: dict[str, list[str]] = defaultdict(list)
    unowned: list[str] = []
    reached_via: dict[str, str] = {}
    for path in external:
        package, via = owner_of(path, owner)
        if package:
            by_package[package].append(path)
            if via != path:
                reached_via[path] = via
        else:
            unowned.append(path)

    flows_in = [p for p in external if p.endswith(FLOWS_IN)]
    document = {
        'schema': 'brickwright/external-inputs/v1',
        'source': source,
        'root': str(root),
        'counts': counts | {
            'external': len(external),
            'owned': len(external) - len(unowned),
            'unowned': len(unowned),
            'packages': len(by_package),
            'flows_into_image': len(flows_in),
        },
        'packages': {
            package: {
                'paths': len(files),
                'flows_into_image': sorted(p for p in files if p.endswith(FLOWS_IN)),
                'licence': licence_of(package),
            }
            for package, files in sorted(by_package.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        },
        'reached_through_symlinks': dict(sorted(reached_via.items())),
        'unowned': sorted(unowned),
    }
    Path(arguments.out).write_text(json.dumps(document, indent=2) + '\n')
    print(f'external {len(external)}  owned {len(external) - len(unowned)} '
          f'by {len(by_package)} packages  unowned {len(unowned)}  '
          f'flowing into the image {len(flows_in)}')
    print(f'wrote {arguments.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
