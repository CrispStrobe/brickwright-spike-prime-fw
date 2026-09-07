#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build=$(mktemp -d /tmp/brickwright-sound.XXXXXX)
trap 'rm -rf "$build"' EXIT
cc -std=gnu11 -Wall -Wextra -Werror -pthread \
  -I"$root/apps/btsensor/test/include" -I"$root/apps/btsensor" \
  -I"$root/bluetooth/zephyr_compat/include" \
  "$root/apps/btsensor/btsensor_sound.c" \
  "$root/apps/btsensor/btsensor_scheduler.c" \
  "$root/apps/btsensor/test/test_btsensor_sound.c" \
  -o "$build/test_btsensor_sound"
"$build/test_btsensor_sound"
