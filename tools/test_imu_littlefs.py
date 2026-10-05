#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise calibration replacement with real build-pinned LittleFS and power cuts."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("littlefs", type=Path)
    source = parser.parse_args().littlefs.resolve()
    for name in ("lfs.c", "lfs.h", "lfs_util.c", "lfs_util.h", "LICENSE.md"):
        print(f"{name}: sha256={hashlib.sha256((source / name).read_bytes()).hexdigest()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="bw-imu-lfs-crash-") as temp:
        work = Path(temp)
        (work / "nuttx/mm").mkdir(parents=True)
        (work / "nuttx/mm/mm.h").write_text("/* Host allocator shim. */\n")
        (work / "fs_heap.h").write_text("#include <stdlib.h>\n#define fs_heap_malloc malloc\n#define fs_heap_free free\n")
        binary = work / "test"
        subprocess.run(["cc", "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
            "-Wno-sign-compare", "-D_DEFAULT_SOURCE", "-DLFS_NO_DEBUG", "-DLFS_NO_WARN",
            "-DLFS_NO_ERROR", "-DLFS_NAME_MAX=32", "-DLFS_FILE_MAX=2147483647",
            "-DLFS_ATTR_MAX=1022", "-I" + str(source), "-I" + str(work),
            "-I" + str(ROOT / "apps/imu"), str(ROOT / "tools/test_imu_littlefs.c"),
            str(source / "lfs.c"), str(source / "lfs_util.c"), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
