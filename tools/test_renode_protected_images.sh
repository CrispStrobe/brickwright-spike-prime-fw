#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
renode_dir=${RENODE_DIR:-"$repo_dir/.local/tools/renode-1.16.1"}
venv_dir=${RENODE_TEST_VENV:-"$repo_dir/.local/tools/renode-test-venv"}

test -x "$renode_dir/renode-test"
test -x "$venv_dir/bin/python"
PATH="$venv_dir/bin:$PATH"
export PATH

exec "$renode_dir/renode-test" \
    --results-dir "$repo_dir/.local/renode-protected-results" \
    --stop-on-error \
    "$@" \
    "$repo_dir/simulation/renode/protected-images.robot"
