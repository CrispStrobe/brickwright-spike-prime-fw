#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_dir=$(mktemp -d /tmp/brickwright-btsensor-scheduler.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
mkdir -p "$build_dir/include/nuttx"
touch "$build_dir/include/nuttx/config.h"

cc -std=gnu11 -Wall -Wextra -Werror -pthread \
  -I"$build_dir/include" \
  -I"$root/apps/btsensor" \
  "$root/apps/btsensor/btsensor_scheduler.c" \
  "$root/apps/btsensor/test/test_scheduler.c" \
  -o "$build_dir/test_scheduler"

"$build_dir/test_scheduler"
echo "btsensor scheduler checks passed"
