#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d /tmp/brickwright-btsensor-classic.XXXXXX)
trap 'rm -rf "$work"' EXIT
cc -std=gnu11 -Wall -Wextra -Werror \
  -I"$root/apps/btsensor" -I"$root/bluetooth/zephyr_compat/include" \
  "$root/apps/btsensor/btsensor_classic.c" \
  "$root/apps/btsensor/test/test_btsensor_classic.c" \
  -o "$work/test-btsensor-classic"
"$work/test-btsensor-classic"
