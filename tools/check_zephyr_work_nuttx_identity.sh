#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Work-queue thread identity must not depend on pthread_self(): on NuttX it
# returns 0 on the work-queue threads. Builds the compat work queue and its
# test with pthread_self() replaced by a model of that behaviour.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/brickwright-work-identity.XXXXXX")
trap 'rm -rf "$work"' EXIT
source=${1:-"$root/bluetooth/zephyr_compat/src/work.c"}
cc -std=gnu11 -Wall -Wextra -Werror -pthread -include zephyr/autoconf.h \
  -I"$root/bluetooth/zephyr_compat/include" \
  -I"$root/third_party/zephyr-host/upstream/subsys/bluetooth/host" \
  -Dpthread_self=nuttx_pthread_self \
  "$source" \
  "$root/third_party/zephyr-host/upstream/subsys/bluetooth/host/long_wq.c" \
  "$root/bluetooth/zephyr_compat/test/nuttx_pthread_self.c" \
  "$root/bluetooth/zephyr_compat/test/test_work.c" \
  -o "$work/test-work-nuttx-identity"
timeout 30 "$work/test-work-nuttx-identity"
echo "zephyr work queue: thread identity holds with NuttX pthread_self()"
