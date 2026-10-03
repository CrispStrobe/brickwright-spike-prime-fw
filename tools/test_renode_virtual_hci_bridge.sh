#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/brickwright-renode-hci.XXXXXX")
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
  if ! grep -qx 'CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI=y' "$root/nuttx/.config"; then
    echo "virtual HCI firmware test requires explicit CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI=y and a rebuilt simulation image" >&2
    exit 2
  fi
  renode_dir=${RENODE_DIR:-"$root/.local/tools/renode-1.16.1"}
  venv_dir=${RENODE_TEST_VENV:-"$root/.local/tools/renode-test-venv"}
  renode_test=${RENODE_TEST:-"$renode_dir/renode-test"}
  PATH="$venv_dir/bin:$PATH"
  export PATH
  renode_tag=${BRICKWRIGHT_RENODE_TAG:-brickwright-simulation-hci}
  # Keep enough host time for the measured full erased-media scan. Explicit
  # existing-filesystem HCI scenarios retain the shorter bound.
  case "$renode_tag" in
    brickwright-simulation-hci|brickwright-erased-simulation-hci) renode_timeout=960s ;;
    *) renode_timeout=300s ;;
  esac
  # Choose an available endpoint after the host bridge checks have closed
  # their sockets. A fixed port can collide with a previous ephemeral peer.
  hci_port=$(python3 - <<'PORT'
import socket
with socket.socket() as listener:
    listener.bind(("0.0.0.0", 0))
    print(listener.getsockname()[1])
PORT
  )
  timeout "$renode_timeout" "$renode_test" --variable "HCI_BRIDGE:$work/renode-virtual-hci" \
    --variable "HCI_PORT:$hci_port" \
    --variable "PLATFORM:@$root/simulation/renode/spike-prime-custom-dma.repl" \
    --include "$renode_tag" \
    --results-dir "$root/.local/renode-results" \
    "$root/simulation/renode/protected-images.robot"
fi
