#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_dir=$(mktemp -d /tmp/brickwright-btsensor-scheduler.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
mkdir -p "$build_dir/include/nuttx"
touch "$build_dir/include/nuttx/config.h"

cc -std=gnu11 -Wall -Wextra -Werror -pthread \
  -I"$build_dir/include" \
  -I"$root/apps/btsensor" \
  "$root/apps/btsensor/btsensor_scheduler.c" \
  "$root/apps/btsensor/test/test_scheduler.c" \
  -o "$build_dir/test_scheduler"

"$build_dir/test_scheduler"
cc -std=gnu11 -Wall -Wextra -Werror -pthread -Dpoll=controlled_poll \
  -I"$build_dir/include" -I"$root/apps/btsensor" \
  -c "$root/apps/btsensor/btsensor_scheduler.c" -o "$build_dir/scheduler_poll.o"
cc -std=gnu11 -Wall -Wextra -Werror -pthread \
  -I"$root/apps/btsensor" "$build_dir/scheduler_poll.o" \
  "$root/apps/btsensor/test/test_scheduler_poll_stop.c" \
  -o "$build_dir/test_scheduler_poll_stop"
"$build_dir/test_scheduler_poll_stop"
echo "btsensor scheduler checks passed"
