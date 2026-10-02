#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

version=3.6.2
url=https://github.com/Mbed-TLS/mbedtls/archive/refs/tags/mbedtls-3.6.2.tar.gz
expected=a3c959773bc5d5b22353bc605e96d92fae2eac486dcaf46990412b84a1a0fb5f
framework_url=https://github.com/Mbed-TLS/mbedtls-framework/archive/df3307f2b4fe512def60886024f7be8fd1523ccd.tar.gz
framework_expected=641fbb913f3ea6748cecbacb30af698d96de585f33d627f12b3ef9275b79726a
destination=${1:?usage: fetch_mbedtls.sh DESTINATION}

if [[ -e "$destination" ]]; then
  echo "destination already exists: $destination" >&2
  exit 1
fi

archive=$(mktemp /tmp/brickwright-mbedtls.XXXXXX.tar.gz)
framework_archive=$(mktemp /tmp/brickwright-mbedtls-framework.XXXXXX.tar.gz)
stage=$(mktemp -d /tmp/brickwright-mbedtls.XXXXXX)
trap 'rm -f "$archive" "$framework_archive"; rm -rf "$stage"' EXIT
curl --fail --location --silent --show-error "$url" --output "$archive"
actual=$(sha256sum "$archive" | cut -d' ' -f1)
if [[ "$actual" != "$expected" ]]; then
  echo "Mbed TLS archive checksum mismatch: expected $expected, got $actual" >&2
  exit 1
fi
tar -xf "$archive" -C "$stage" --strip-components=1
grep -q 'Apache-2.0' "$stage/LICENSE"
curl --fail --location --silent --show-error "$framework_url" \
  --output "$framework_archive"
framework_actual=$(sha256sum "$framework_archive" | cut -d' ' -f1)
if [[ "$framework_actual" != "$framework_expected" ]]; then
  echo "Mbed TLS framework checksum mismatch: expected $framework_expected, got $framework_actual" >&2
  exit 1
fi
mkdir -p "$stage/framework"
tar -xf "$framework_archive" -C "$stage/framework" --strip-components=1
mv "$stage" "$destination"
trap 'rm -f "$archive" "$framework_archive"' EXIT
echo "prepared Mbed TLS $version at $destination"
