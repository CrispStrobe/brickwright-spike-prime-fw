#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d /tmp/brickwright-btsensor-compile.XXXXXX)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/include/nuttx"
touch "$work/include/nuttx/config.h"

common=(
  -std=gnu11 -Wall -Wextra
  -I"$work/include"
  -I"$root/apps/btsensor/test/include"
  -I"$root/apps/btsensor"
  -I"$root/bluetooth/daemon"
  -I"$root/bluetooth/zephyr_compat/include"
  -I"$root/protocol/c"
)
portable=(
  apps/btsensor/btsensor_main.c
  apps/btsensor/btsensor_cmd_neutral.c
  apps/btsensor/btsensor_classic.c
  apps/btsensor/btsensor_modern.c
  apps/btsensor/btsensor_modern_backend.c
  apps/btsensor/btsensor_tx.c
  bluetooth/daemon/hub_protocol.c
  protocol/c/spike_codec.c
)

for source in "${portable[@]}"; do
  cc "${common[@]}" -c "$root/$source" -o "$work/native-$(basename "${source%.c}").o"
done

cross=${CROSS_COMPILE:-arm-none-eabi-}gcc
config=${NUTTX_CONFIG:-$root/nuttx/include/nuttx/config.h}
if command -v "$cross" >/dev/null && [[ -s "$config" ]]; then
  arm_common=(
    -std=gnu11 -mcpu=cortex-m4 -mthumb -Wall -Wextra -D__NuttX__
    -include "$config" -include zephyr/autoconf.h
    -I"$(dirname "$(dirname "$config")")"
    -I"$root/apps/btsensor"
    -I"$root/bluetooth/daemon"
    -I"$root/bluetooth/zephyr_compat/include"
    -I"$root/protocol/c"
    -I"$root/third_party/zephyr-host/upstream/include"
    -I"$root/third_party/zephyr-host/upstream/subsys/bluetooth"
  )
  arm_sources=("${portable[@]}" apps/btsensor/btsensor_lifecycle.c apps/btsensor/btsensor_transport.c)
  for source in "${arm_sources[@]}"; do
    "$cross" "${arm_common[@]}" -c "$root/$source" \
      -o "$work/arm-$(basename "${source%.c}").o" 2>"$work/arm.err" ||
      { cat "$work/arm.err" >&2; exit 1; }
  done
else
  echo "ARM compile skipped: compiler or configured NuttX tree unavailable" >&2
fi

echo "btsensor neutral compile: OK"
