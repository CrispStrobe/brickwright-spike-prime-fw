#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:?Usage: build.sh OUTPUT_DIRECTORY}
mkdir -p "$out"
arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -O2 -ffreestanding -fno-builtin -nostdlib -Wl,--build-id=none -T "$here/link.ld" "$here/main.c" -o "$out/arena-demo.elf"
if test -n "$(arm-none-eabi-nm -u "$out/arena-demo.elf")"; then
    echo "Unexpected runtime dependency" >&2
    exit 1
fi
