#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d /tmp/brickwright-host-link.XXXXXX)
trap 'rm -rf "$work"' EXIT
"$root/tools/fetch_mbedtls.sh" "$work/mbedtls"
cmake -S "$work/mbedtls" -B "$work/mbedtls-build" \
  -DENABLE_PROGRAMS=OFF -DENABLE_TESTING=OFF \
  -DUSE_SHARED_MBEDTLS_LIBRARY=OFF -DUSE_STATIC_MBEDTLS_LIBRARY=ON >/dev/null
cmake --build "$work/mbedtls-build" --target mbedcrypto -j2 >/dev/null

mapfile -t sources < <(python3 - "$root/third_party/zephyr-host/manifest.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for paths in data["source_groups"].values():
    for path in paths:
        if path.endswith(".c") and path != "drivers/bluetooth/hci/h4.c":
            print(path)
PY
)
objects=()
flags=(
  -std=gnu11 -w -pthread -DCONFIG_ZTEST=1
  -DMBEDTLS_CONFIG_FILE='"mbedtls/mbedtls_config.h"'
  -include stdbool.h -include zephyr/autoconf.h
  -I"$root/bluetooth/zephyr_compat/include"
  -I"$root/third_party/zephyr-host/upstream/include"
  -I"$root/third_party/zephyr-host/upstream/subsys/bluetooth"
  -I"$work/mbedtls/include"
)
for source in "${sources[@]}"; do
  object="$work/${source//\//-}.o"
  extra=()
  if [[ "$source" == subsys/bluetooth/host/crypto_psa.c ]]; then
    extra+=( -Dbt_rand=brickwright_unused_psa_rand )
  fi
  cc "${flags[@]}" "${extra[@]}" -c \
    "$root/third_party/zephyr-host/upstream/$source" -o "$object"
  objects+=("$object")
done
for source in entropy hex log settings uuid work h4 controller_lifecycle ehcill h4_transport h4_netbuf virtual_hci hci_driver fd02_service classic_spp hub_transport; do
  object="$work/compat-$source.o"
  cc "${flags[@]}" -c "$root/bluetooth/zephyr_compat/src/$source.c" -o "$object"
  objects+=("$object")
done
cc "${flags[@]}" -c "$root/bluetooth/ti_service_pack/ti_bts_loader.c" \
  -o "$work/ti-bts-loader.o"
objects+=("$work/ti-bts-loader.o")
cc "${flags[@]}" -c "$root/bluetooth/zephyr_compat/test/test_host_link.c" \
  -o "$work/test-host-link.o"
cc -pthread -Wl,--gc-sections "${objects[@]}" "$work/test-host-link.o" \
  "$work/mbedtls-build/library/libmbedcrypto.a" -o "$work/host-link"
timeout 30 "$work/host-link"
size "$work/host-link"
