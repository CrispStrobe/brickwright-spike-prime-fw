#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build=$(mktemp -d /tmp/brickwright-btsensor-tx.XXXXXX)
trap 'rm -rf "$build"' EXIT
cc -std=gnu11 -Wall -Wextra -Werror -pthread \
  -DCONFIG_APP_BTSENSOR_RING_DEPTH=4 \
  -I"$root/apps/btsensor" -I"$root/bluetooth/zephyr_compat/include" \
  "$root/apps/btsensor/btsensor_tx.c" \
  "$root/apps/btsensor/test/test_btsensor_tx.c" -o "$build/test_btsensor_tx"
"$build/test_btsensor_tx"
