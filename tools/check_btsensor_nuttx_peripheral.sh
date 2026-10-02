#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/.." && pwd)
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT
cc -std=c11 -Wall -Wextra -Werror -I"$repo_root/apps/btsensor" \
  -I"$repo_root/bluetooth/zephyr_compat/include" \
  "$repo_root/apps/btsensor/btsensor_nuttx_peripheral.c" \
  "$repo_root/apps/btsensor/test/test_btsensor_nuttx_peripheral.c" \
  -o "$build_dir/test_btsensor_nuttx_peripheral"
"$build_dir/test_btsensor_nuttx_peripheral"
