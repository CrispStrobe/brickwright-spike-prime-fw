#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
set -euo pipefail
ulimit -c 0
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build=$(mktemp -d "${TMPDIR:-/tmp}/brickwright-btsensor-tx-links.XXXXXX")
trap 'rm -rf "$build"' EXIT
cc -std=gnu11 -Wall -Wextra -Werror -pthread \
  -DCONFIG_APP_BTSENSOR_RING_DEPTH=4 \
  -I"$root/apps/btsensor" -I"$root/bluetooth/zephyr_compat/include" \
  "$root/apps/btsensor/btsensor_tx.c" \
  "$root/apps/btsensor/test/test_btsensor_tx_links.c" -o "$build/test"
"$build/test"
