#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Verify deterministic ROMFS bytes, checksums, link targets and contents."""
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from make_romfs import make_image


def parse_image(image):
    """Independent format reader, using only serialized offsets."""
    assert image[:8] == b'-rom1fs-'
    size = struct.unpack_from('>I', image, 8)[0]
    assert size <= len(image) and len(image) % 1024 == 0
    assert sum(struct.unpack(f'>{min(size,512)//4}I', image[:min(size,512)])) & 0xffffffff == 0
    end = image.index(0, 16)
    root = (end + 16) & ~15
    entries = {}

    def header(offset):
        assert offset % 16 == 0 and offset + 16 < size
        following, special, length, check = struct.unpack_from('>IIII', image, offset)
        end = image.index(0, offset + 16)
        body = (end + 16) & ~15
        raw = image[offset:body]
        assert sum(struct.unpack(f'>{len(raw)//4}I',raw)) & 0xffffffff == 0
        name = os.fsdecode(image[offset + 16:end])
        assert body + length <= size
        return following & ~15, following & 7, bool(following & 8), special, name, image[body:body+length]

    def visit(offset, path, parent):
        following, kind, executable, special, name, data = header(offset)
        assert kind in (1, 2, 3)
        entries[path] = (kind, executable, data)
        if kind == 1:
            child = special
            seen = set()
            dots = set()
            while child:
                assert child not in seen
                seen.add(child)
                nxt, typ, ex, target, childname, childdata = header(child)
                if childname in ('.', '..'):
                    dots.add(childname)
                    # genromfs may use the root directory as its own '.' entry.
                    assert typ == 0 or child == offset
                    if typ == 0:
                        assert target == (offset if childname == '.' else parent)
                else:
                    assert childname and '/' not in childname
                    visit(child, path + '/' + childname, offset)
                child = nxt
            assert dots == {'.', '..'}
    visit(root, '', root)
    return entries


class RomfsTests(unittest.TestCase):
    def test_creation_order_metadata_and_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            one, two = Path(temp)/'one', Path(temp)/'two'
            for root, names in ((one,['z','a','middle']), (two,['middle','a','z'])):
                root.mkdir(mode=0o755)
                for name in names:
                    folder=root/name;folder.mkdir(mode=0o755)
                    for filename,data in [('empty',b''),('script',b'echo hello\n'),('binary',bytes(range(256)))]:
                        (folder/filename).write_bytes(data)
                        (folder/filename).chmod(0o755 if filename=='script' else 0o644)
                    (folder/'link').symlink_to('script')
            for path in two.rglob('*'):
                if not path.is_symlink():
                    os.utime(path,(12345,12345))
            first, second = make_image(one), make_image(two)
            self.assertEqual(first,second)
            entries=parse_image(first)
            self.assertEqual(entries['/a/script'],(2,True,b'echo hello\n'))
            self.assertEqual(entries['/a/empty'],(2,False,b''))
            self.assertEqual(entries['/z/binary'],(2,False,bytes(range(256))))
            self.assertEqual(entries['/middle/link'],(3,False,b'script'))
            self.assertEqual(len(entries),16)

    def test_boot_root_traversal_and_disconnected_root_mutation(self):
        # NuttX starts root enumeration at the first file header. Opening the
        # init script must work from that sibling chain as well as spec-info.
        def read_script(image):
            root = (image.index(0, 16) + 16) & ~15
            start = root
            for component in ('init.d', 'rcS'):
                seen = set()
                while start:
                    self.assertNotIn(start, seen)
                    seen.add(start)
                    following, special, size, unused = struct.unpack_from('>IIII', image, start)
                    end = image.index(0, start + 16)
                    name = image[start + 16:end].decode()
                    if name == component:
                        if component == 'rcS':
                            body = (end + 16) & ~15
                            return image[body:body + size]
                        start = special
                        break
                    start = following & ~15
                else:
                    raise FileNotFoundError(component)
            raise AssertionError('script not reached')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'init.d').mkdir()
            script = b'hubprogram serve\n'
            (root/'init.d/rcS').write_bytes(script)
            image = make_image(root)
            self.assertEqual(read_script(image), script)
            self.assertEqual(parse_image(image)['/init.d/rcS'][2], script)
            mutant = bytearray(image)
            offset = (mutant.index(0, 16) + 16) & ~15
            following = struct.unpack_from('>I', mutant, offset)[0]
            struct.pack_into('>I', mutant, offset, following & 15)
            # Remove the root's sibling link: this was the mounted-but-empty
            # root regression. Lookup must detect it before firmware packaging.
            with self.assertRaises(FileNotFoundError):
                read_script(mutant)

    def test_unsupported_input_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            os.mkfifo(Path(temp)/'fifo')
            with self.assertRaises(ValueError):
                make_image(Path(temp))

    def test_invalid_volume(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                make_image(Path(temp),'bad\0name')


if __name__ == '__main__':
    unittest.main()
