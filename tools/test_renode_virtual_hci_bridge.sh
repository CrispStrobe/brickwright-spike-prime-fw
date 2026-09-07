#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d /tmp/brickwright-renode-hci.XXXXXX)
trap 'rm -rf "$work"' EXIT

cc -std=c11 -Wall -Wextra -Werror -D_POSIX_C_SOURCE=200809L \
  -I"$root/bluetooth/zephyr_compat/include" \
  "$root/tools/renode_virtual_hci_bridge.c" \
  "$root/bluetooth/zephyr_compat/src/h4.c" \
  "$root/bluetooth/zephyr_compat/src/virtual_hci.c" \
  -o "$work/renode-virtual-hci"

python3 "$root/tools/test_renode_virtual_hci_bridge.py" \
  "$work/renode-virtual-hci"

if [[ "${BRICKWRIGHT_RENODE_FIRMWARE_TEST:-0}" == 1 ]]; then
  renode_dir=${RENODE_DIR:-"$root/.local/tools/renode-1.16.1"}
  venv_dir=${RENODE_TEST_VENV:-"$root/.local/tools/renode-test-venv"}
  renode_test=${RENODE_TEST:-"$renode_dir/renode-test"}
  PATH="$venv_dir/bin:$PATH"
  export PATH
  timeout 300s "$renode_test" --variable "HCI_BRIDGE:$work/renode-virtual-hci" \
    --variable "HCI_PORT:34561" \
    --variable "PLATFORM:@$root/simulation/renode/spike-prime-custom-dma.repl" \
    --include brickwright-hci \
    "$root/simulation/renode/protected-images.robot"
fi
