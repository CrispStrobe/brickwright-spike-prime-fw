#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output=${1:?usage: build_zephyr_nuttx_archive.sh OUTPUT_ARCHIVE}
compiler=${CROSS_COMPILE:-arm-none-eabi-}gcc
archiver=${CROSS_COMPILE:-arm-none-eabi-}ar
config=${NUTTX_CONFIG:-$root/nuttx/include/nuttx/config.h}
work=$(mktemp -d /tmp/brickwright-zephyr-nuttx-archive.XXXXXX)
owned_mbedtls=

cleanup()
{
  rm -rf "$work"
  if [[ -n "$owned_mbedtls" ]]; then
    rm -rf "$owned_mbedtls"
  fi
}
trap cleanup EXIT

test -s "$config"
command -v "$compiler" >/dev/null
command -v "$archiver" >/dev/null

if [[ -n "${MBEDTLS_SOURCE_DIR:-}" ]]; then
  mbedtls_source=$MBEDTLS_SOURCE_DIR
else
  owned_mbedtls=$(mktemp -d /tmp/brickwright-mbedtls-source.XXXXXX)
  mbedtls_source=$owned_mbedtls/source
  "$root/tools/fetch_mbedtls.sh" "$mbedtls_source"
fi
test -f "$mbedtls_source/include/psa/crypto.h"

# shellcheck source=tools/zephyr_nuttx_sources.sh
source "$root/tools/zephyr_nuttx_sources.sh"

flags=(
  -std=gnu11 -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
  -Os -ffunction-sections -fdata-sections
  -Wall -Wextra -Wno-unused-parameter -D__NuttX__
  -DMBEDTLS_CONFIG_FILE='"brickwright/mbedtls_nuttx_config.h"'
  -include "$config" -include zephyr/autoconf.h
  -I"$root/bluetooth/zephyr_compat/include"
  -I"$root/third_party/zephyr-host/upstream/include"
  -I"$root/third_party/zephyr-host/upstream/subsys/bluetooth"
  -I"$mbedtls_source/include" -I"$root/nuttx/include"
)

objects=()
for source in "${zephyr_nuttx_sources[@]}"; do
  object="$work/zephyr-${source//\//-}.o"
  source_flags=()
  if [[ "$source" == third_party/zephyr-host/upstream/subsys/bluetooth/* ]]; then
    source_flags+=( -DCONFIG_ZTEST=1 )
  fi
  if [[ "$source" == */host/crypto_psa.c ]]; then
    source_flags+=( -Dbt_rand=brickwright_unused_psa_rand )
  fi
  "$compiler" "${flags[@]}" "${source_flags[@]}" -c "$root/$source" -o "$object"
  objects+=("$object")
done

# Mbed TLS keeps the authoritative source list and dependencies in CMake.
# Cross-build only libmbedcrypto, then flatten its objects into our archive so
# the protected NuttX application has one ordered, self-contained dependency.
cmake -S "$mbedtls_source" -B "$work/mbedtls-build" \
  -DCMAKE_SYSTEM_NAME=Generic \
  -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY \
  -DCMAKE_C_COMPILER="$compiler" \
  -DCMAKE_C_FLAGS="-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -Os -ffunction-sections -fdata-sections -D__NuttX__ -DMBEDTLS_CONFIG_FILE=\\\"brickwright/mbedtls_nuttx_config.h\\\" -include $config -I$root/nuttx/include -I$root/bluetooth/zephyr_compat/include" \
  -DENABLE_TESTING=OFF -DENABLE_PROGRAMS=OFF -DUSE_SHARED_MBEDTLS_LIBRARY=OFF \
  >/dev/null
cmake --build "$work/mbedtls-build" --target mbedcrypto -j2 >/dev/null
while IFS= read -r object; do
  objects+=("$object")
done < <(find "$work/mbedtls-build" -type f \
  \( -name '*.o' -o -name '*.obj' \) \
  -path '*/library/CMakeFiles/mbedcrypto.dir/*' -print | LC_ALL=C sort)
test "${#objects[@]}" -gt "${#zephyr_nuttx_sources[@]}"

mkdir -p "$(dirname "$output")"
rm -f "$output"
"$archiver" crD "$output" "${objects[@]}"
"$archiver" s "$output"
test -s "$output"
echo "prepared $output (${#objects[@]} objects)"
