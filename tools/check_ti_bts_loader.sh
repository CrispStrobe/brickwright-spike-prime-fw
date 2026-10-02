#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output=${TMPDIR:-/tmp}/brickwright-test-ti-bts-loader

cc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I"$root/bluetooth/ti_service_pack" \
  "$root/bluetooth/ti_service_pack/ti_bts_loader.c" \
  "$root/bluetooth/ti_service_pack/test_ti_bts_loader.c" \
  -o "$output"
"$output"

cc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I"$root/apps/btsensor" \
  -I"$root/bluetooth/zephyr_compat/include" \
  "$root/apps/btsensor/btsensor_ti_payload.c" \
  "$root/apps/btsensor/test/test_ti_payload.c" \
  -o "${output}-payload"
"${output}-payload"
