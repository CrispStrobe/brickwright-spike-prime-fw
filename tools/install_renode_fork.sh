#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
# Build the reviewed runtime and every native translator from pinned source.
# Standard NuGet packages and Renode's pinned support libraries remain build
# dependencies; this does not download a prebuilt Renode executable/runtime.
set -euo pipefail

runtime_revision=3b2a6041fe612b65c369024d2115e9fab6dabc24
infrastructure_revision=03a59657a17de8833189dd3c29a11353643c0c31
resources_revision=14b80cde0a136b684f316eb7f6a31aeaae0684bf
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tools_dir=${BRICKWRIGHT_TOOLS_DIR:-"$repo_dir/.local/tools"}
runtime_dir="$tools_dir/renode-fork-$runtime_revision"
venv_dir="$tools_dir/renode-fork-test-venv-$runtime_revision"

case ${1:-} in
    --print-runtime) printf '%s\n' "$runtime_dir"; exit 0 ;;
    --print-venv) printf '%s\n' "$venv_dir"; exit 0 ;;
    '') ;;
    *) printf 'Usage: %s [--print-runtime|--print-venv]\n' "$0" >&2; exit 2 ;;
esac

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    echo 'This reviewed runtime build currently targets Linux x86_64.' >&2
    exit 1
fi
for command_name in git dotnet cmake make gcc g++ python3; do
    command -v "$command_name" >/dev/null || {
        printf 'Required build command missing: %s\n' "$command_name" >&2
        exit 1
    }
done

checkout_revision() {
    local directory=$1 url=$2 revision=$3
    if [[ ! -e "$directory" ]]; then
        mkdir -p "$directory"
        git -C "$directory" init --quiet
        git -C "$directory" remote add origin "$url"
        git -C "$directory" fetch --depth 1 --no-tags origin "$revision"
        git -C "$directory" checkout --detach FETCH_HEAD
    fi
    if [[ $(git -C "$directory" rev-parse HEAD) != "$revision" ]]; then
        printf 'Refusing to modify a checkout with an unexpected revision: %s\n' "$directory" >&2
        exit 1
    fi
    git -C "$directory" diff --quiet
    git -C "$directory" diff --cached --quiet
    if [[ -n $(git -C "$directory" ls-files --others --exclude-standard) ]]; then
        printf 'Untracked source files require review before building: %s\n' "$directory" >&2
        exit 1
    fi
}

mkdir -p "$tools_dir"
checkout_revision "$runtime_dir" \
    https://github.com/CrispStrobe/renode-spike-prime.git "$runtime_revision"
expected_infrastructure=$(git -C "$runtime_dir" ls-tree HEAD src/Infrastructure | awk '{print $3}')
if [[ "$expected_infrastructure" != "$infrastructure_revision" ]]; then
    echo 'Reviewed runtime has an unexpected Infrastructure gitlink.' >&2
    exit 1
fi

git -C "$runtime_dir" submodule update --init --recursive --depth 1
git -C "$runtime_dir" submodule foreach --recursive \
    'test "$(git rev-parse HEAD)" = "$sha1" && git diff --quiet && git diff --cached --quiet && test -z "$(git ls-files --others --exclude-standard)"'
test "$(git -C "$runtime_dir/src/Infrastructure" rev-parse HEAD)" = "$infrastructure_revision"
checkout_revision "$runtime_dir/lib/resources" \
    https://github.com/renode/renode-resources.git "$resources_revision"

# --skip-fetch preserves the verified submodule and support-library pins.
# Build all native architectures first, then the complete managed solution.
(
    cd "$runtime_dir"
    ./build.sh --net --no-gui --skip-fetch --external-lib-only
    ./build.sh --net --no-gui --skip-fetch
)

if [[ ! -x "$venv_dir/bin/python" ]]; then
    python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/pip" install --disable-pip-version-check \
    -r "$runtime_dir/tests/requirements.txt"

"$venv_dir/bin/python" - "$runtime_dir" "$runtime_revision" \
    "$infrastructure_revision" "$resources_revision" \
    "$tools_dir/renode-fork-$runtime_revision.build-receipt.json" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
files = [root / "output/bin/Release/Renode.dll",
         root / "output/bin/Release/Infrastructure.dll"]
files += sorted((root / "src/Infrastructure/src/Emulator/Cores/bin/Release/lib").glob("*.so"))
if not files or any(not path.is_file() for path in files):
    raise SystemExit("runtime build outputs are missing")
if not any(path.name == "translate-arm-m-le.so" for path in files):
    raise SystemExit("Cortex-M native translator is missing")
receipt = {
    "runtime_revision": sys.argv[2],
    "infrastructure_revision": sys.argv[3],
    "resources_revision": sys.argv[4],
    "build": "all native translators and full headless managed solution from source",
    "dotnet_sdk": subprocess.check_output(["dotnet", "--version"], text=True).strip(),
    "gcc": subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0],
    "sha256": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in files},
}
Path(sys.argv[5]).write_text(json.dumps(receipt, indent=2) + "\n")
PY
"$runtime_dir/renode" --version
printf 'RENODE_DIR=%s\nRENODE_TEST_VENV=%s\n' "$runtime_dir" "$venv_dir"
