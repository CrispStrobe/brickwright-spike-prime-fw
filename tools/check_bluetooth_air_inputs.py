#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the qualified host air sources, package versions and installed notices."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--air-tools', required=True, type=Path)
    args = parser.parse_args()
    record = json.loads((ROOT / 'policy/bluetooth-air-host-inputs.json').read_text())
    requirements = ROOT / 'tools/bluetooth-air-requirements.txt'
    if hashlib.sha256(requirements.read_bytes()).hexdigest() != record['requirements_sha256']:
        raise SystemExit('Bluetooth-air requirements differ from reviewed inputs')
    for source, expected in record['air_files_sha256'].items():
        path = args.air_tools / Path(source).name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit('Bluetooth-air source differs: ' + source)
    for package in record['packages']:
        distribution = importlib.metadata.distribution(package['name'])
        if distribution.version != package['version']:
            raise SystemExit('Bluetooth-air package version differs: ' + package['name'])
        for notice in package['installed_license_files']:
            path = distribution.locate_file(notice['path'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != notice['sha256']:
                raise SystemExit('Installed Bluetooth-air notice differs: ' + notice['path'])
    print('Bluetooth-air: qualified source/package versions and installed notice hashes verified')


if __name__ == '__main__':
    main()
