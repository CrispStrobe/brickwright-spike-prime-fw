#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT

cc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I"$root/apps/btsensor" -I"$root/protocol/c" \
  "$root/apps/btsensor/btsensor_modern.c" \
  "$root/protocol/c/spike_codec.c" \
  "$root/apps/btsensor/test_btsensor_modern.c" \
  -o "$build/test_btsensor_modern"
"$build/test_btsensor_modern"

cc -std=c11 -Wall -Wextra -Werror -pedantic -pthread \
  -I"$root/apps/btsensor" \
  "$root/apps/btsensor/btsensor_modern.c" \
  "$root/apps/btsensor/btsensor_modern_notify.c" \
  "$root/apps/btsensor/test_btsensor_modern_notify.c" \
  -o "$build/test_btsensor_modern_notify"
"$build/test_btsensor_modern_notify"
