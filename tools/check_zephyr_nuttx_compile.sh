#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
size_tool=${CROSS_COMPILE:-arm-none-eabi-}size

build_dir=$(mktemp -d /tmp/brickwright-zephyr-nuttx.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
archive="$build_dir/libbrickwright_zephyr_host.a"
"$root/tools/build_zephyr_nuttx_archive.sh" "$archive"
"$size_tool" "$archive"
${CROSS_COMPILE:-arm-none-eabi-}ar t "$archive" | grep -F 'crypto_psa.c.o' >/dev/null
