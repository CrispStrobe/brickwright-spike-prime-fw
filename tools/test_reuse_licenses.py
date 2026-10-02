#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Mutation tests for attribution, licence expressions and input drift."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from check_reuse_licenses import check


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if isinstance(data, dict) else data)


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    write(root/'policy/source-policy.json', {'allowed_project_licenses': ['MIT', 'BSD-3-Clause']})
    text = '// Pybricks source\n// Copyright (c) 2023 Original Author\n// SPDX-License-Identifier: MIT\n'
    source = root/'apps/fixture.c'
    write(source, text)
    reuse = {'files': [{'path': 'apps/fixture.c', 'reference_sources': ['original.c'],
                        'selected_licences': ['MIT'], 'sha256': hashlib.sha256(text.encode()).hexdigest()}],
             'upstream_files': [{'path': 'original.c', 'copyrights': ['Copyright (c) 2023 Original Author']}],
             'required_notices': ['licenses/MIT.txt'],
             'notice_sha256': {'licenses/MIT.txt': hashlib.sha256(b'fixture grant').hexdigest()}}
    write(root/'policy/pybricks-reuse.json', reuse)
    write(root/'policy/micropython-embed.json', {'files': [], 'required_notices': []})
    write(root/'policy/orientation-filter.json', {
        'files': [], 'selected_licence': 'MIT',
        'required_notices': ['licenses/MIT.txt'],
        'notice_sha256': {'licenses/MIT.txt': hashlib.sha256(b'fixture grant').hexdigest()}})
    write(root/'licenses/MIT.txt', 'fixture grant')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    assert not check(root)
    source.write_text(text.replace('Original Author', 'Someone Else'))
    reuse['files'][0]['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    write(root/'policy/pybricks-reuse.json', reuse)
    assert any('missing original notice' in x for x in check(root))
    source.write_text(text)
    reuse['files'][0]['sha256'] = hashlib.sha256(text.encode()).hexdigest()
    write(root/'policy/pybricks-reuse.json', reuse)
    write(root/'apps/injected.c', '// SPDX-License-Identifier: MIT AND CC-BY-SA-4.0\n')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    assert any('outside source policy' in x for x in check(root))
    write(root/'apps/injected.c', '// SPDX-License-Identifier: MIT OR GPL-2.0-only\n')
    assert not check(root)
    write(root/'apps/injected.c', '// Pybricks source with no inventory\n')
    assert any('absent from inventory' in x for x in check(root))
    write(root/'apps/injected.c', '// SPDX-License-Identifier: MIT\n// https://stackoverflow.com/a/123\n')
    assert any('answer provenance' in x for x in check(root))
    write(root/'apps/injected.c', '// SPDX-License-Identifier: MIT\n')
    write(root/'third_party/micropython-embed/py/new.c', '// MIT\n')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    assert any('MicroPython file set changed' in x for x in check(root))
    write(root/'licenses/MIT.txt', 'truncated')
    assert any('changed or truncated' in x for x in check(root))
    (root/'licenses/MIT.txt').unlink()
    assert any('required licence text' in x for x in check(root))
print('reuse-licence mutation checks passed')
