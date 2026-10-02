#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python3 "$root/tools/apply_nuttx_backports.py" --check
compiler=${CROSS_COMPILE:-arm-none-eabi-}gcc
runtime=$("$compiler" -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -print-libgcc-file-name)
python3 "$root/tools/collect_build_inputs.py" --root "$root" \
  --dependency-root "$root" \
  --include-embed-inventory "$root/policy/micropython-embed.json" \
  --input "$root/apps/hubprogram/micropython/brickwright_module.c" \
  --input "$root/boards/spike-prime-hub/scripts/memory.ld" \
  --input "$root/boards/spike-prime-hub/scripts/kernel-space.ld" \
  --input "$root/boards/spike-prime-hub/scripts/user-space.ld" \
  --output "$root/build/simulation-inputs.json"
python3 "$root/tools/check_firmware_inputs.py" \
  --inputs "$root/build/simulation-inputs.json" \
  --inputs "$root/build/nuttx-bluetooth/libbrickwright_zephyr_host.a.inputs.json" \
  --runtime-archive "$runtime" --config "$root/nuttx/.config" \
  --link-map "$root/nuttx/nuttx.map" --link-map "$root/nuttx/nuttx_user.map"
python3 "$root/tools/check_ti_free_image.py" \
  "$root/nuttx/nuttx.bin" "$root/nuttx/nuttx_user.bin" \
  --config "$root/nuttx/.config" --elf "$root/nuttx/nuttx" --elf "$root/nuttx/nuttx_user.elf" \
  --build-root "$root/nuttx" --build-root "$root/nuttx-apps" --build-root "$root/apps"
