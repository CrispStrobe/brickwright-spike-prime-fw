#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Export compiler dependency evidence and original notices, without classifying licences."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex


def version_metadata_digest(text):
    # Tag availability changes version facts in shallow/full checkouts. Only
    # literal facts are normalized; added code, directives and notices remain.
    text = re.sub(r'^(#define CONFIG_VERSION_(?:MAJOR|MINOR|PATCH))\s+\d+\s*$',
                  r'\1 <VCS_METADATA>', text, flags=re.M)
    text = re.sub(r'^(#define CONFIG_VERSION_(?:STRING|BUILD))\s+"[A-Za-z0-9_.+-]*"\s*$',
                  r'\1 <VCS_METADATA>', text, flags=re.M)
    return hashlib.sha256(text.encode()).hexdigest()


def collect(root, directories, aliases=(), inventory=None, explicit=()):
    files, units, missing, cache = {}, [], [], {}

    def key(path):
        for prefix, label in aliases:
            if path.is_relative_to(prefix):
                return label + '/' + path.relative_to(prefix).as_posix()
        if path.is_relative_to(root):
            return path.relative_to(root).as_posix()
        return 'toolchain:' + path.as_posix()

    def record(path):
        name = key(path)
        if name not in files:
            data = path.read_bytes()
            text = data.decode(errors='replace')
            # Keep entire comments containing grant/attribution evidence.
            comments = re.findall(r'/\*[\s\S]*?\*/', text)
            notices = [c for c in comments if re.search(
                r'copyright|SPDX-|permission|redistribution|public domain|licen[cs]e', c, re.I)]
            files[name] = {'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                           'spdx': [x.strip() for x in re.findall(
                               r'SPDX-License-Identifier:\s*([^\n*]+)', text)],
                           'notices': notices}
            if name == 'nuttx/include/nuttx/version.h':
                files[name]['version_metadata_sha256'] = version_metadata_digest(text)
        return name

    dependencies = set()
    for directory in directories:
        for pattern in ('Make.dep', '*.d'):
            dependencies.update(p for p in directory.rglob(pattern) if p.is_file())
    for dep in sorted(dependencies):
        for line in dep.read_text(errors='replace').replace('\\\n', ' ').splitlines():
            if not line or line.startswith('#') or ':' not in line:
                continue
            target, raw = line.split(':', 1)
            if not re.search(r'\.(?:o|obj)(?:\s|$)', target):
                continue
            inputs = []
            for token in shlex.split(raw):
                if token.startswith('$') or token == '|':
                    continue
                path = Path(token)
                cache_key = token if path.is_absolute() else (str(dep.parent), token)
                if cache_key not in cache:
                    candidates = [path] if path.is_absolute() else [
                        a / path for a in [dep.parent, *list(dep.parents)[:6]]]
                    cache[cache_key] = next((p.resolve() for p in candidates if p.is_file()), None)
                path = cache[cache_key]
                if path is None:
                    missing.append({'dependency_file': key(dep), 'input': token})
                else:
                    inputs.append(record(path))
            if inputs:
                units.append({'target': target.strip(), 'inputs': inputs})
    # Embed rules can omit compiler dependency output; cover the complete
    # reviewed interpreter selection conservatively rather than omit it.
    if inventory:
        for item in json.loads(inventory.read_text())['files']:
            if Path(item['path']).suffix in ('.c', '.h'):
                record((root / 'third_party/micropython-embed' / item['path']).resolve())
    for path in explicit:
        record(path.resolve())
    return {'schema': 1, 'scope': 'Conservative compiler inputs; not a licence decision or exact linked-line count.',
            'dependency_files': len(dependencies), 'files': sorted(files.values(), key=lambda x: x['path']),
            'units': units, 'unresolved': missing}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--dependency-root', type=Path, action='append', required=True)
    parser.add_argument('--alias', action='append', default=[], help='absolute directory=stable label')
    parser.add_argument('--include-embed-inventory', type=Path)
    parser.add_argument('--input', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    aliases = [(Path(value.split('=', 1)[0]).resolve(), value.split('=', 1)[1]) for value in args.alias]
    result = collect(args.root.resolve(), args.dependency_root, aliases, args.include_embed_inventory, args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'build-inputs: {len(result["files"])} files, {len(result["units"])} units, '
          f'{len(result["unresolved"])} unresolved dependencies')
    if result['unresolved']:
        raise SystemExit('Unresolved compiler inputs; audit is incomplete')


if __name__ == '__main__':
    main()
