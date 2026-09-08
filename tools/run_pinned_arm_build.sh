#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 TOOLCHAIN_ROOT COMMAND [ARG ...]" >&2
    exit 2
fi

toolchain_root=$(realpath "$1")
shift
repo_root=$(cd "$(dirname "$0")/.." && pwd)
python3 -I "$repo_root/tools/toolchain_boundary.py" \
    --lock "$repo_root/policy/arm-toolchain.lock.json" \
    --toolchain-root "$toolchain_root"

clean_home=$(mktemp -d)
trap 'rm -r "$clean_home"' EXIT
exec env -i \
    HOME="$clean_home" \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC SOURCE_DATE_EPOCH=0 \
    PATH="$toolchain_root/bin:/usr/bin:/bin" \
    PYTHONNOUSERSITE=1 PYTHONHASHSEED=0 \
    CROSS_COMPILE=arm-none-eabi- \
    "$@"
