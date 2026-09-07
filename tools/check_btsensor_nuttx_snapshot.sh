#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$repo_root/tools/check_legosensor_latest.py"
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT
cc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I"$repo_root/apps/btsensor/test/include" \
  -I"$repo_root/apps/btsensor" \
  "$repo_root/apps/btsensor/btsensor_nuttx_snapshot.c" \
  "$repo_root/apps/btsensor/test/test_btsensor_nuttx_snapshot.c" \
  -o "$build_dir/test_btsensor_nuttx_snapshot"
"$build_dir/test_btsensor_nuttx_snapshot"
