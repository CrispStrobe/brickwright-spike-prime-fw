#!/usr/bin/env python3
"""Prove, from the artifacts, that no copyleft-scoped newlib source is in the link.

newlib's notice is an aggregate of twenty-eight licences, two of which are
copyleft: entry (21), the FSF LGPL, "(*-linux* targets only)", and entry (22),
Xavier Leroy's LGPL, "(i[3456]86-*-linux* targets only)".  Both are excluded by
target for an arm-none-eabi build — but that exclusion rests on a parenthetical
annotation in a text file, which is a reading, not evidence about the artifact.

This makes it a fact about the artifact.  For each archive or object the build
capture showed as a link input, it reports every member's ELF machine type and
searches the member names and their contents for the markers those two entries
carry ("GNU C Library", "Xavier Leroy", "sysdeps", and linux/i386 path
fragments).  An object compiled for *-linux* or i386 cannot be an ARM object,
and a member derived from glibc's sysdeps carries its name or its notice.

  tools/linked_object_licences.py --out <json> <archive-or-object> ...

Reports; declares nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# The markers entries (21) and (22) carry, and the trees they live in.
COPYLEFT_MARKERS = (b'GNU C Library', b'Xavier Leroy', b'sysdeps')
COPYLEFT_NAMES = re.compile(r'linux|i[3456]86|sysdep', re.IGNORECASE)


def members(path: Path) -> list[str]:
    if path.suffix != '.a':
        return [path.name]
    result = subprocess.run(['ar', 't', str(path)], capture_output=True, text=True, check=False)
    return [line for line in result.stdout.split('\n') if line.strip()]


def machines(path: Path) -> dict[str, int]:
    """ELF machine type of every member, counted."""
    counts: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as work:
        if path.suffix == '.a':
            subprocess.run(['ar', 'x', str(path)], cwd=work, check=False,
                           capture_output=True)
            objects = sorted(Path(work).glob('*.o'))
        else:
            copy = Path(work) / path.name
            shutil.copy(path, copy)
            objects = [copy]
        for obj in objects:
            result = subprocess.run(['readelf', '-h', str(obj)],
                                    capture_output=True, text=True, check=False)
            machine = 'unreadable'
            for line in result.stdout.split('\n'):
                if line.strip().startswith('Machine:'):
                    machine = line.split(':', 1)[1].strip()
                    break
            counts[machine] = counts.get(machine, 0) + 1
    return counts


def marker_hits(path: Path) -> list[str]:
    data = path.read_bytes()
    return [marker.decode() for marker in COPYLEFT_MARKERS if marker in data]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('inputs', nargs='+')
    arguments = parser.parse_args()

    report = {}
    for name in arguments.inputs:
        path = Path(name)
        if not path.exists():
            report[name] = {'present': False}
            continue
        listing = members(path)
        report[name] = {
            'present': True,
            'members': len(listing),
            'machines': machines(path),
            'members_named_for_copyleft_trees': [m for m in listing if COPYLEFT_NAMES.search(m)],
            'copyleft_markers_in_bytes': marker_hits(path),
        }

    clean = all(
        entry.get('present')
        and not entry['members_named_for_copyleft_trees']
        and not entry['copyleft_markers_in_bytes']
        and set(entry['machines']) <= {'ARM'}
        for entry in report.values()
    )
    document = {
        'schema': 'brickwright/linked-object-licences/v1',
        'question': 'is any newlib source under entry (21) FSF LGPL (*-linux* targets only) '
                    'or entry (22) Xavier Leroy LGPL (i[3456]86-*-linux* targets only) '
                    'present in the link?',
        'answer': 'no' if clean else 'inconclusive — see the entries',
        'basis': 'every member is an ARM object, no member is named for the linux/i386 '
                 'trees those entries live in, and no member carries their notices',
        'inputs': report,
    }
    Path(arguments.out).write_text(json.dumps(document, indent=2) + '\n')
    for name, entry in report.items():
        if entry.get('present'):
            print(f'{name}: {entry["members"]} member(s), machines {entry["machines"]}, '
                  f'copyleft-named {len(entry["members_named_for_copyleft_trees"])}, '
                  f'markers {entry["copyleft_markers_in_bytes"]}')
        else:
            print(f'{name}: absent')
    print(f'answer: {document["answer"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
