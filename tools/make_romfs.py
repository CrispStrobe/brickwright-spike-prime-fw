#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Create a deterministic ROMFS image for the board's preprocessed init tree.

Format specification: https://docs.kernel.org/filesystems/romfs.html
This implementation supports directories, regular files and symbolic links;
it deliberately rejects device nodes, FIFOs and sockets. Names are ordered by
encoded bytes, never by host readdir order. No timestamps or inode numbers are
encoded. This is an original format implementation, not genromfs source.
"""
import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
import struct


@dataclass(eq=False)
class Node:
    name: bytes
    kind: int
    executable: bool = False
    data: bytes = b''
    target: 'Node | None' = None
    children: list = field(default_factory=list)
    following: 'Node | None' = None
    offset: int = 0


def padded(data, alignment=16):
    return data + bytes((-len(data)) % alignment)


def tree(path, name, parent=None):
    mode = path.lstat().st_mode
    if stat.S_ISDIR(mode):
        node = Node(name, 1, bool(mode & 0o111))
        node.children = [Node(b'.', 0, target=node),
                         Node(b'..', 0, target=parent or node)]
        for child in sorted(path.iterdir(), key=lambda p: os.fsencode(p.name)):
            node.children.append(tree(child, os.fsencode(child.name), node))
        for first, second in zip(node.children, node.children[1:]):
            first.following = second
        return node
    if stat.S_ISREG(mode):
        return Node(name, 2, bool(mode & 0o111), path.read_bytes())
    if stat.S_ISLNK(mode):
        return Node(name, 3, data=os.fsencode(os.readlink(path)))
    raise ValueError(f'unsupported ROMFS input type: {path}')


def flatten(node):
    yield node
    for child in node.children:
        yield from flatten(child)


def checksum(data):
    assert len(data) % 4 == 0
    return (-sum(struct.unpack(f'>{len(data)//4}I', data))) & 0xffffffff


def make_image(directory, volume='NSHInitVol'):
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('ROMFS root must be a real directory')
    volume_name = volume.encode('utf-8')
    if b'\0' in volume_name:
        raise ValueError('NUL in volume name')
    root = tree(directory, b'.')
    # The root header is also its own '.' directory entry. NuttX begins
    # root traversal at this header and follows siblings, while other readers
    # begin at its special-info pointer. Both must reach the same child list.
    root.children.pop(0)
    root.following = root.children[0]
    nodes = list(flatten(root))
    prefix = b'-rom1fs-' + bytes(8) + padded(volume_name + b'\0')
    offset = len(prefix)
    for node in nodes:
        if b'\0' in node.name:
            raise ValueError('NUL in file name')
        node.offset = offset
        offset += 16 + len(padded(node.name + b'\0')) + len(padded(node.data))
    if offset > 0xffffffff:
        raise ValueError('ROMFS image exceeds 32-bit format')
    image = bytearray(prefix)
    for node in nodes:
        next_and_mode = (node.following.offset if node.following else 0)
        next_and_mode |= node.kind | (8 if node.executable else 0)
        special = (node.offset if node is root else node.children[0].offset) if node.kind == 1 else 0
        if node.kind == 0:
            special = node.target.offset
        header = bytearray(struct.pack('>IIII', next_and_mode, special,
                                       len(node.data), 0) + padded(node.name + b'\0'))
        struct.pack_into('>I', header, 12, checksum(header))
        image.extend(header)
        image.extend(padded(node.data))
    struct.pack_into('>I', image, 8, len(image))
    struct.pack_into('>I', image, 12, checksum(image[:512]))
    return padded(bytes(image), 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-d', type=Path, required=True)
    parser.add_argument('-f', type=Path, required=True)
    parser.add_argument('-V', default='NSHInitVol')
    args = parser.parse_args()
    try:
        args.f.write_bytes(make_image(args.d, args.V))
    except (OSError, ValueError) as exc:
        parser.exit(1, f'ROMFS generation failed: {exc}\n')


if __name__ == '__main__':
    main()
