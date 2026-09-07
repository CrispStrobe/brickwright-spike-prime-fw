#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
output=$(mktemp "${TMPDIR:-/tmp}/brickwright-controller-lifecycle.XXXXXX")
trap 'rm -f "$output"' EXIT
cc -std=gnu11 -Wall -Wextra -Werror \
  -I"$root/bluetooth/zephyr_compat/include" \
  "$root/bluetooth/zephyr_compat/src/controller_lifecycle.c" \
  "$root/bluetooth/zephyr_compat/test/test_controller_lifecycle.c" \
  -o "$output"
"$output"
