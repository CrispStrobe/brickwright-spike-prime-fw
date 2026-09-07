#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
compiler=${CROSS_COMPILE:-arm-none-eabi-}gcc
size_tool=${CROSS_COMPILE:-arm-none-eabi-}size
build_dir=$(mktemp -d /tmp/brickwright-psa-build.XXXXXX)
owned_source=
if [[ -n "${MBEDTLS_SOURCE_DIR:-}" ]]; then
  mbedtls_source=$MBEDTLS_SOURCE_DIR
else
  mbedtls_source=$(mktemp -u /tmp/brickwright-mbedtls-source.XXXXXX)
  "$root/tools/fetch_mbedtls.sh" "$mbedtls_source"
  owned_source=$mbedtls_source
fi
cleanup()
{
  rm -rf "$build_dir"
  if [[ -n "$owned_source" ]]; then
    rm -rf "$owned_source"
  fi
}
trap cleanup EXIT
test -f "$mbedtls_source/include/psa/crypto.h"

flags=(
  -std=gnu11 -mcpu=cortex-m4 -mthumb -Wall -Wextra -Wno-unused-parameter
  -D__NuttX__ -DCONFIG_ZTEST=1
  -DMBEDTLS_CONFIG_FILE='"mbedtls/mbedtls_config.h"'
  -include "$root/nuttx/include/nuttx/config.h"
  -include zephyr/autoconf.h
  -I"$root/bluetooth/zephyr_compat/include"
  -I"$root/third_party/zephyr-host/upstream/include"
  -I"$root/third_party/zephyr-host/upstream/subsys/bluetooth"
  -I"$mbedtls_source/include"
  -I"$root/nuttx/include"
)
sources=(
  subsys/bluetooth/host/crypto_psa.c
  subsys/bluetooth/host/ecc.c
  subsys/bluetooth/crypto/bt_crypto.c
  subsys/bluetooth/crypto/bt_crypto_psa.c
)
objects=()
for source in "${sources[@]}"; do
  object="$build_dir/${source//\//-}.o"
  source_flags=()
  if [[ "$source" == subsys/bluetooth/host/crypto_psa.c ]]; then
    # Hardware RNG ownership remains in the NuttX entropy boundary.
    source_flags+=( -Dbt_rand=brickwright_unused_psa_rand )
  fi
  "$compiler" "${flags[@]}" "${source_flags[@]}" -c \
    "$root/third_party/zephyr-host/upstream/$source" -o "$object"
  objects+=("$object")
done
"$size_tool" "${objects[@]}"
