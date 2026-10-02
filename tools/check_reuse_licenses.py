#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Check source reuse inventories; this is not a complete firmware link audit."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    errors = []
    policy = json.loads((root / 'policy/source-policy.json').read_text())
    allowed = set(policy['allowed_project_licenses'])
    reuse = json.loads((root / 'policy/pybricks-reuse.json').read_text())
    mp = json.loads((root / 'policy/micropython-embed.json').read_text())
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    tracked = {p for p in tracked if p}
    listed = {x['path']: x for x in reuse['files']}
    sources = {x['path']: x for x in reuse['upstream_files']}
    for rel in tracked:
        if Path(rel).suffix not in {'.c', '.h', '.cpp', '.cs', '.S'}:
            continue
        text = (root / rel).read_text(errors='replace')
        if re.search(r'CC[- ]BY[- ]SA|creativecommons.org/licenses/by-sa|stackoverflow.com/(?:a/|questions/)', text, re.I):
            errors.append(f'{rel}: share-alike material or answer provenance requires review')
        for expression in re.findall(r'SPDX-License-Identifier:\s*([^\n*]+)', text):
            # OR permits selecting an allowed branch; AND requires every term.
            alternatives = re.split(r'\s+OR\s+', expression)
            if not any({x.strip(' ()') for x in re.split(r'\s+AND\s+', a)} <= allowed for a in alternatives):
                errors.append(f'{rel}: licence expression outside source policy: {expression}')
        if rel.startswith(('apps/', 'boards/')) and re.search(r'pybricks', text, re.I) and rel not in listed:
            errors.append(f'{rel}: Pybricks source/reference absent from inventory')
    for rel, item in listed.items():
        path = root / rel
        if rel not in tracked or not path.exists():
            errors.append(f'{rel}: inventoried source is not tracked')
            continue
        text = path.read_text()
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            errors.append(f'{rel}: source changed; update reviewed inventory')
        for source in item['reference_sources']:
            if source not in sources:
                errors.append(f'{rel}: unresolved source reference {source}')
                continue
            for notice in sources[source]['copyrights']:
                if notice not in text:
                    errors.append(f'{rel}: missing original notice: {notice}')
        if not set(item['selected_licences']) <= allowed:
            errors.append(f'{rel}: unapproved source licence')
    mp_root = root / 'third_party/micropython-embed'
    recorded = {x['path'] for x in mp['files']}
    actual = {p[len('third_party/micropython-embed/'):] for p in tracked if p.startswith('third_party/micropython-embed/')}
    if recorded != actual:
        errors.append(f'MicroPython file set changed: added={sorted(actual-recorded)}, missing={sorted(recorded-actual)}')
    for item in mp['files']:
        path = mp_root / item['path']
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            errors.append(f'MicroPython/{item["path"]}: changed or missing pinned input')
        if item['licence'] not in allowed:
            errors.append(f'MicroPython/{item["path"]}: unapproved licence')
    for name in reuse['required_notices'] + mp['required_notices']:
        if name not in tracked or not (root / name).is_file():
            errors.append(f'{name}: required licence text is not tracked')
    for inventory in (reuse, mp):
        for name, digest in inventory.get('notice_sha256', {}).items():
            path = root / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                errors.append(f'{name}: required licence text changed or truncated')
    orientation = json.loads((root / 'policy/orientation-filter.json').read_text())
    for item in orientation['files']:
        path = root / item['path']
        if item['path'] not in tracked or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            errors.append(f'{item["path"]}: changed or missing reviewed orientation adapter')
        elif 'Copyright (c) 2021 x-io Technologies' not in path.read_text():
            errors.append(f'{item["path"]}: missing Fusion copyright')
    if orientation['selected_licence'] not in allowed:
        errors.append('Orientation adapter: unapproved licence')
    for name in orientation['required_notices']:
        path = root / name
        if name not in tracked or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != orientation['notice_sha256'].get(name):
            errors.append(f'{name}: required Fusion licence text changed or missing')
    return errors


if __name__ == '__main__':
    problems = check()
    if problems:
        raise SystemExit('\n'.join(problems))
    print('reuse-licences: Pybricks, MicroPython and Fusion attribution/inventories verified')
    print('reuse-licences: source check only; external NuttX/toolchain linkage and TI hardware images are separate')
