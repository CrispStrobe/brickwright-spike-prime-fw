#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu

version=1.16.1
archive_sha256=00e113cdbd0f5354cf2f64bbe3f5a070d8958409542fca66e45ac97d982938c0
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tools_dir=${BRICKWRIGHT_TOOLS_DIR:-"$repo_dir/.local/tools"}
archive="$tools_dir/renode-$version.linux-portable-dotnet.tar.gz"
install_dir="$tools_dir/renode-$version"
venv_dir="$tools_dir/renode-test-venv"

mkdir -p "$tools_dir" "$install_dir"
if [ ! -f "$archive" ]; then
    curl -fL --retry 3 \
        "https://github.com/renode/renode/releases/download/v$version/renode-$version.linux-portable-dotnet.tar.gz" \
        -o "$archive"
fi
printf '%s  %s\n' "$archive_sha256" "$archive" | sha256sum -c -

if [ ! -x "$install_dir/renode" ]; then
    tar -xzf "$archive" -C "$install_dir" --strip-components=1
fi

if [ ! -x "$venv_dir/bin/python" ]; then
    python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/pip" install --disable-pip-version-check \
    -r "$install_dir/tests/requirements.txt"
"$install_dir/renode" --version
