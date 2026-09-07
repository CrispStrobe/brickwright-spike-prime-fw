#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
renode_dir=${RENODE_DIR:-"$repo_dir/.local/tools/renode-1.16.1"}
venv_dir=${RENODE_TEST_VENV:-"$repo_dir/.local/tools/renode-test-venv"}

test -x "$renode_dir/renode"
test -x "$venv_dir/bin/python"
test -f "$repo_dir/.local/firmware-images/manifest.json"

PATH="$venv_dir/bin:$PATH"
export PATH

exec "$renode_dir/renode-test" \
    --results-dir "$repo_dir/.local/renode-results" \
    --stop-on-error \
    "$repo_dir/simulation/renode/opaque-images.robot"
