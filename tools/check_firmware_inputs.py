#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Check a simulation build against reviewed source/runtime inputs and notice texts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import posixpath

ROOT = Path(__file__).resolve().parents[1]


def check(documents, review, runtime_digest, config):
    errors, actual, version_metadata = [], {}, {}
    for document in documents:
        if document.get('unresolved'):
            errors.append('Unresolved compiler dependencies')
        for item in document['files']:
            name = item['path']
            if name in actual and actual[name] != item['sha256']:
                errors.append(f'{name}: conflicting compiler input hashes')
            actual[name] = item['sha256']
            if 'version_metadata_sha256' in item:
                version_metadata[name] = item['version_metadata_sha256']
    expected = {item['path']: item for item in review['files']}
    for name in sorted(actual.keys() - expected.keys()):
        errors.append(f'{name}: unreviewed compiler input')
    for name in sorted(expected.keys() - actual.keys()):
        errors.append(f'{name}: reviewed input absent; configured build changed')
    for name in actual.keys() & expected.keys():
        item = expected[name]
        normalized_match = ('version_metadata_sha256' in item and
                            version_metadata.get(name) == item['version_metadata_sha256'])
        if actual[name] != item['sha256'] and not normalized_match:
            errors.append(f'{name}: reviewed compiler input changed')
        if not item['selected_licences'] or not set(item['selected_licences']) <= set(review['accepted_licences']):
            errors.append(f'{name}: unapproved licence selection')
    if runtime_digest != review['compiler_runtime']['archive_sha256']:
        errors.append('Compiler runtime archive changed; review its source/licence and linked members')
    errors += check_configuration(config, review)
    return errors


def check_configuration(config, review):
    errors = []
    if 'CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK=y' not in config.splitlines():
        errors.append('This inventory covers the simulation profile only')
    if hashlib.sha256(config.encode()).hexdigest() != review['config_sha256']:
        errors.append('Configured build changed; review the selected component closure')
    return errors


def notices(root, review):
    errors = []
    for item in review['files']:
        if not item['selected_licences'] or not set(item['selected_licences']) <= set(review['accepted_licences']):
            errors.append(f'{item["path"]}: unapproved licence selection')
        name = item['path']
        if name.startswith(('apps/', 'boards/', 'bluetooth/', 'third_party/')):
            path = root / name
            # Generated ROMFS inputs need the configured build; tracked source
            # is also checked in source-only CI without external submodules.
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                errors.append(f'{name}: source changed since the configured-build audit')
    for name, digest in review['notice_sha256'].items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f'{name}: redistribution notice missing or changed')
    return errors


def link_inputs(maps, root):
    archives, direct, paths = {}, set(), {}
    encoded_root = str(root).replace('/', '.')
    def key(name):
        name = posixpath.normpath(name)
        if name.startswith(str(root) + '/'):
            return name[len(str(root)) + 1:]
        return ('toolchain:' if name.startswith('/') else 'relative:') + name
    for text in maps:
        selected = text.split('Allocating common symbols')[0].split('Discarded input sections')[0]
        for path, member in re.findall(r'^(\S+\.a)\(([^)]+)\)', selected, re.M):
            archives.setdefault(Path(path).name, set()).add(member.replace(encoded_root, 'ROOT'))
            paths.setdefault(Path(path).name, set()).add(key(path))
        for name in re.findall(r'^LOAD (\S+)$', text, re.M):
            if not name.endswith('.a'):
                direct.add(key(name))
    return archives, direct, paths


def check_links(maps, root, review):
    archives, direct, paths = link_inputs(maps, root)
    expected = {name: set(item['members']) for name, item in review['archives'].items()}
    errors = []
    if archives != expected:
        errors.append('Linker-selected archive/member set changed; review binary dependencies')
    if direct != set(review['direct_objects']):
        errors.append('Direct linker object set changed; review binary dependencies')
    if paths != {name: set(values) for name, values in review['archive_paths'].items()}:
        errors.append('Linked archive paths changed; review binary dependencies')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, default=ROOT/'policy/simulation-firmware-inputs.json')
    parser.add_argument('--inputs', type=Path, action='append', default=[])
    parser.add_argument('--runtime-archive', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--link-map', type=Path, action='append', default=[])
    parser.add_argument('--notices-only', action='store_true')
    parser.add_argument('--config-only', action='store_true')
    parser.add_argument('--require-clearance', action='store_true',
                        help='also refuse unresolved source-origin/history findings')
    args = parser.parse_args()
    review = json.loads(args.inventory.read_text())
    errors = notices(ROOT, review)
    from check_source_origin_review import check_record, clearance_errors
    origin_review = json.loads((ROOT/'policy/source-origin-review.json').read_text())
    errors += check_record(ROOT, origin_review)
    if args.require_clearance:
        errors += clearance_errors(origin_review)
    if args.config_only:
        if not args.config:
            parser.error('--config-only requires --config')
        errors += check_configuration(args.config.read_text(), review)
    elif not args.notices_only:
        if not args.inputs or not args.runtime_archive or not args.config or not args.link_map:
            parser.error('supply --inputs, --runtime-archive, --config and --link-map, or use --notices-only')
        errors += check([json.loads(p.read_text()) for p in args.inputs], review,
                        hashlib.sha256(args.runtime_archive.read_bytes()).hexdigest(), args.config.read_text())
        errors += check_links([p.read_text() for p in args.link_map], ROOT, review)
    if errors:
        raise SystemExit('\n'.join(errors))
    if args.config_only:
        print('firmware-inputs: simulation configuration/notices verified before compilation')
    elif args.notices_only:
        print('firmware-inputs: redistribution notice hashes verified')
    else:
        print('firmware-inputs: reviewed simulation inputs, linker dependencies and notices verified')
    if clearance_errors(origin_review):
        print('firmware-inputs: open source-origin/history findings; successful input checks are not redistribution clearance')


if __name__ == '__main__':
    main()
