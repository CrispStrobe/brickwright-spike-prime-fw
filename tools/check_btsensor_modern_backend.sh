#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build=$(mktemp -d /tmp/brickwright-modern-backend.XXXXXX)
trap 'rm -rf "$build"' EXIT

cc -std=gnu11 -Wall -Wextra -Werror \
  -I"$root/apps/btsensor/test/include" -I"$root/apps/btsensor" \
  -I"$root/bluetooth/zephyr_compat/include" \
  "$root/apps/btsensor/btsensor_modern_backend.c" \
  "$root/apps/btsensor/test/test_btsensor_modern_backend.c" \
  -o "$build/test_btsensor_modern_backend"
"$build/test_btsensor_modern_backend"
