#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise compiler-input drift, failed dependency resolution and notice loss."""
from copy import deepcopy
from pathlib import Path
import hashlib
import tempfile
from collect_build_inputs import collect, version_metadata_digest
from check_firmware_inputs import check, notices, check_links

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root/'init.d').mkdir()
    (root/'fixture.c').write_text('// SPDX-License-Identifier: MIT\n#include "fixture.h"\n')
    (root/'fixture.h').write_text('// SPDX-License-Identifier: MIT\n')
    (root/'Make.dep').write_text('fixture.o: fixture.c \\\n fixture.h\n')
    result = collect(root, [root])
    if result['unresolved'] or len(result['files']) != 2:
        raise SystemExit('Dependency collection failed')
    # Embed rules can omit .d files: the authored wrapper must be an explicit
    # input, independent of retained interpreter source coverage.
    wrapper = root/'wrapper.c'
    wrapper.write_text('/* SPDX-License-Identifier: BSD-3-Clause */\nint wrapper;\n')
    explicit_result = collect(root, [root], explicit=[wrapper])
    explicit_files = {x['path']: x for x in explicit_result['files']}
    if set(explicit_files) != {'fixture.c', 'fixture.h', 'wrapper.c'}:
        raise SystemExit('Authored wrapper without dependencies omitted')
    if explicit_files['wrapper.c']['sha256'] != hashlib.sha256(wrapper.read_bytes()).hexdigest():
        raise SystemExit('Explicit wrapper fingerprint incorrect')
    wrapper.write_text(wrapper.read_text() + 'int changed;\n')
    changed_explicit = collect(root, [root], explicit=[wrapper])
    changed_files = {x['path']: x for x in changed_explicit['files']}
    if changed_files['wrapper.c']['sha256'] == explicit_files['wrapper.c']['sha256']:
        raise SystemExit('Explicit wrapper change not detected')
    digest = hashlib.sha256(b'runtime').hexdigest()
    review = {'files': [{**x, 'selected_licences': ['MIT']} for x in result['files']],
              'accepted_licences': ['MIT'], 'compiler_runtime': {'archive_sha256': digest},
              'notice_sha256': {'LICENSE': hashlib.sha256(b'grant').hexdigest()}}
    config = 'CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK=y\n'
    review['config_sha256'] = hashlib.sha256(config.encode()).hexdigest()
    if check([result], review, digest, config):
        raise SystemExit('Valid inputs rejected')
    for mutation in ('changed', 'added', 'missing', 'unresolved'):
        bad = deepcopy(result)
        if mutation == 'changed': bad['files'][0]['sha256'] = 'other'
        if mutation == 'added': bad['files'].append({'path': 'extra.c', 'sha256': 'extra'})
        if mutation == 'missing': bad['files'].pop()
        if mutation == 'unresolved': bad['unresolved'] = ['unknown.h']
        if not check([bad], review, digest, config):
            raise SystemExit(f'Input mutation accepted: {mutation}')
    bad = deepcopy(review)
    bad['files'][0]['selected_licences'] = ['GPL-3.0-only']
    if not check([result], bad, digest, config):
        raise SystemExit('Bare GPL selection accepted')
    if not check([result], review, 'changed-runtime', config):
        raise SystemExit('Runtime change accepted')
    if not check([result], review, digest, ''):
        raise SystemExit('Hardware config accepted')
    if not check([result], review, digest, config + 'CONFIG_NEW_FEATURE=y\n'):
        raise SystemExit('Config drift accepted')
    (root/'LICENSE').write_text('grant')
    if notices(root, review): raise SystemExit('Valid grant rejected')
    (root/'LICENSE').write_text('truncated')
    if not notices(root, review): raise SystemExit('Truncated grant accepted')
    (root/'Make.dep').write_text('fixture.o: missing.h\n')
    if not collect(root, [root])['unresolved']:
        raise SystemExit('Missing dependency accepted')
    review['archives'] = {'libfixture.a': {'members': {'fixture.o': 'hash'}}}
    review['direct_objects'] = ['relative:startup.o']
    review['archive_paths'] = {'libfixture.a': ['toolchain:/build/libfixture.a']}
    linked = '/build/libfixture.a(fixture.o)\nLOAD startup.o\n'
    if check_links([linked], root, review): raise SystemExit('Valid link map rejected')
    if not check_links([linked + '/build/libunknown.a(blob.o)\n'], root, review):
        raise SystemExit('Unreviewed binary archive accepted')
    if not check_links([linked + 'LOAD blob.o\n'], root, review):
        raise SystemExit('Unreviewed direct binary accepted')
    if not check_links([linked + 'LOAD blob.bin\n'], root, review):
        raise SystemExit('Unreviewed embedded binary accepted')
    if not check_links([linked.replace('/build/libfixture.a', '/other/libfixture.a')], root, review):
        raise SystemExit('Substituted archive path accepted')
print('firmware-input mutation checks passed')

version = '#define CONFIG_VERSION_STRING "0.0.0"\n#define CONFIG_VERSION_MAJOR 0\n'
other = '#define CONFIG_VERSION_STRING "12.13.0"\n#define CONFIG_VERSION_MAJOR 12\n'
if version_metadata_digest(version) != version_metadata_digest(other):
    raise SystemExit('Checkout-dependent version facts rejected')
if version_metadata_digest(version) == version_metadata_digest(version + '#include "blob.h"\n'):
    raise SystemExit('Version-header code change hidden')

# Source-only CI deliberately leaves external NuttX dependencies uninitialized.
# A tracked exact grant must stay mandatory without requiring the dependency.
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    grant = root / 'licenses/LittleFS-BSD-3-Clause.txt'
    grant.parent.mkdir()
    grant.write_bytes(b'synthetic retained BSD grant')
    review = {'files': [], 'accepted_licences': ['BSD-3-Clause'],
              'notice_sha256': {'licenses/LittleFS-BSD-3-Clause.txt':
                               hashlib.sha256(grant.read_bytes()).hexdigest()}}
    if (root/'nuttx').exists() or notices(root, review):
        raise SystemExit('Tracked LittleFS grant failed without external dependency')
    grant.unlink()
    if not notices(root, review):
        raise SystemExit('Missing tracked LittleFS grant accepted')
    grant.write_bytes(b'changed grant')
    if not notices(root, review):
        raise SystemExit('Changed tracked LittleFS grant accepted')
