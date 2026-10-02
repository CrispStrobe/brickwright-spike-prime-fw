#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d /tmp/brickwright-hub-daemon.XXXXXX)
trap 'rm -rf "$work"' EXIT
cc -std=c11 -Wall -Wextra -Werror -I"$root/bluetooth/daemon" -I"$root/protocol/c" \
  "$root/protocol/c/spike_codec.c" "$root/bluetooth/daemon/hub_protocol.c" \
  "$root/bluetooth/daemon/test_hub_protocol.c" -o "$work/test-hub-protocol"
"$work/test-hub-protocol"
cc -std=c11 -Wall -Wextra -Werror -I"$root/bluetooth/daemon" \
  -I"$root/protocol/c" -I"$root/bluetooth/zephyr_compat/include" \
  "$root/protocol/c/spike_codec.c" "$root/bluetooth/daemon/hub_protocol.c" \
  "$root/bluetooth/daemon/daemon_transport.c" \
  "$root/bluetooth/daemon/test_daemon_transport.c" -o "$work/test-daemon-transport"
"$work/test-daemon-transport"
