#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Offline candidate discovery, not a licence or independent-authorship verdict.

Read every tracked text file in two Git checkouts, without following
gitlinks. Compare comment/whitespace-insensitive lexical token sequences and
sequences with non-keyword identifiers collapsed. The second pass deliberately
over-reports common declarations, numeric constants and API boilerplate.
Review the original files and their history before interpreting a match.
No source excerpts or downloaded files are included in the output.
"""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess

TOKEN = re.compile(
    r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|'
    r"'(?:\\.|[^'\\])*'|[A-Za-z_]\w*|"
    r'(?:0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?)[uUlLfF]*|[^\s]'
)
KEYWORDS = set(('auto break case char const continue default do double else enum '
                'extern float for goto if inline int long register restrict return '
                'short signed sizeof static struct switch typedef union unsigned '
                'void volatile while bool true false NULL include define ifdef '
                'ifndef endif elif pragma undef and or not def import from class '
                'try except finally raise with yield pass None True False async await').split())
WINDOW = 20


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def tracked_text(root):
    texts, inventory = [], []
    for record in git(root, 'ls-files', '--stage', '-z').decode().split('\0'):
        if not record:
            continue
        metadata, name = record.split('\t', 1)
        mode, object_id, stage = metadata.split()
        if stage != '0':
            raise ValueError(f'unmerged input: {name}')
        if mode == '160000':
            inventory.append({'path': name, 'kind': 'gitlink', 'commit': object_id})
            continue
        if mode == '120000':
            # Audit the link itself; never read an untracked target through it.
            data = git(root, 'cat-file', 'blob', object_id)
        else:
            data = (root / name).read_bytes()
        entry = {'path': name, 'sha256': hashlib.sha256(data).hexdigest()}
        if b'\0' in data:
            entry['kind'] = 'binary-not-token-scanned'
        else:
            text = data.decode('utf-8', errors='replace')
            entry['kind'] = 'text' if mode != '120000' else 'symlink'
            if '\ufffd' in text:
                entry['encoding_note'] = 'Non-UTF-8 bytes replaced; ASCII code tokens remain available.'
            texts.append((name, text))
        inventory.append(entry)
    return texts, inventory


def tokens(text, mode):
    result = []
    for match in TOKEN.finditer(text):
        token = match.group()
        if token.startswith(('/*', '//')):
            continue
        if mode == 'renamed' and re.fullmatch(r'[A-Za-z_]\w*', token) and token not in KEYWORDS:
            token = 'IDENT'
        result.append(token)
    return result


def windows(sequence):
    values = [int.from_bytes(hashlib.blake2b(t.encode(), digest_size=8).digest(), 'big')
              for t in sequence]
    mask, base = (1 << 64) - 1, 1000003
    power = pow(base, WINDOW - 1, 1 << 64)
    digest = 0
    for value in values[:WINDOW]:
        digest = (digest * base + value) & mask
    if len(values) >= WINDOW:
        yield digest, 0
    for i in range(WINDOW, len(values)):
        digest = ((digest - values[i - WINDOW] * power) * base + values[i]) & mask
        yield digest, i - WINDOW + 1


def scan(local, reference, mode, minimum):
    reference_tokens = [tokens(text, mode) for _, text in reference]
    index = {}
    for reference_id, sequence in enumerate(reference_tokens):
        for key, position in windows(sequence):
            if key not in index:
                index[key] = []
            entry = index[key]
            if entry is not None:
                entry.append((reference_id, position))
                if len(entry) > 80:
                    index[key] = None  # Too frequent to be a useful candidate seed.
    results = []
    for name, text in local:
        sequence = tokens(text, mode)
        pairs = defaultdict(list)
        for key, local_position in windows(sequence):
            for reference_id, reference_position in index.get(key) or []:
                # Verify tokens after hashing; hash collisions cannot create a match.
                if sequence[local_position:local_position + WINDOW] == reference_tokens[reference_id][reference_position:reference_position + WINDOW]:
                    pairs[reference_id].append((local_position, reference_position))
        for reference_id, positions in pairs.items():
            diagonals = defaultdict(list)
            for local_position, reference_position in positions:
                diagonals[reference_position - local_position].append(local_position)
            spans = []
            for delta, positions in diagonals.items():
                ordered = sorted(set(positions))
                start = last = ordered[0]
                for position in ordered[1:] + [10**12]:
                    if position == last + 1:
                        last = position
                        continue
                    length = last - start + WINDOW
                    if length >= minimum:
                        spans.append({'local_token': start, 'reference_token': start + delta,
                                      'tokens': length})
                    start = last = position
            if spans:
                results.append({'local': name, 'reference': reference[reference_id][0],
                                'mode': mode, 'longest_tokens': max(s['tokens'] for s in spans),
                                'spans': sorted(spans, key=lambda s: (-s['tokens'], s['local_token']))})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    local, local_inventory = tracked_text(args.local)
    reference, reference_inventory = tracked_text(args.reference)
    matches = scan(local, reference, 'exact', 32) + scan(local, reference, 'renamed', 65)
    report = {
        'schema': 1,
        'method': {'token_window': WINDOW, 'exact_minimum': 32, 'renamed_minimum': 65,
                   'ignored_seed_occurrences_above': 80,
                   'caveat': 'Lexical candidate discovery only. C-style comments are omitted; comments in other languages remain tokens. Submodules and binary assets require separate review. No detection of all paraphrases or proof of absence.'},
        'scanner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'local_revision': git(args.local, 'rev-parse', 'HEAD').decode().strip(),
        'reference_revision': git(args.reference, 'rev-parse', 'HEAD').decode().strip(),
        'local_files': local_inventory, 'reference_files': reference_inventory,
        'matches': sorted(matches, key=lambda m: (m['local'], m['reference'], m['mode'])),
    }
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'similarity: {len(local)} local / {len(reference)} reference text files; {len(matches)} candidates')


if __name__ == '__main__':
    main()
