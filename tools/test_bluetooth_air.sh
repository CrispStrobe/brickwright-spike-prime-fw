#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
renode_dir=${RENODE_DIR:-$("$root/tools/install_renode_fork.sh" --print-runtime)}
air_tools=${BW_AIR_TOOLS:-"$renode_dir/tools/bw-air"}
venv_dir=${BW_AIR_VENV:-"$root/.local/tools/bluetooth-air-venv"}
images=${BW_AIR_IMAGES:-"$root/.local/firmware-images/brickwright-simulation"}
fixture=${BW_AIR_FIXTURE:-"$root/.local/firmware-images/existing-filesystem"}

# These tests execute a freshly built explicit TI-free Bluetooth profile.
for option in CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK CONFIG_APP_BTSENSOR_SIM_VIRTUAL_HCI CONFIG_APP_BTSENSOR_START_VISIBLE; do
    if ! grep -qx "$option=y" "$root/nuttx/.config"; then
        echo "Bluetooth-air gate requires the rebuilt simulation-hci profile: $option" >&2
        exit 2
    fi
done
python3 "$root/tools/check_ti_free_image.py" \
    --config "$root/nuttx/.config" --elf "$images/nuttx" --elf "$images/nuttx_user.elf" \
    "$images/nuttx.bin" "$images/nuttx_user.bin"
test -x "$renode_dir/renode"
test -f "$air_tools/hci_node.py"
if [[ ! -x "$venv_dir/bin/python" ]]; then
    python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install -r "$root/tools/bluetooth-air-requirements.txt"
"$venv_dir/bin/python" -m pip check
"$venv_dir/bin/python" "$root/tools/check_bluetooth_air_inputs.py" --air-tools "$air_tools"
mkdir -p "$root/.local/bluetooth-air-results"
"$venv_dir/bin/python" -m pip freeze > "$root/.local/bluetooth-air-results/packages.txt"
# Load the board while paused as this caller before network isolation. Renode
# fetches/caches the platform's SVD in its normal per-user cache; Robot's CI
# mode may disable that cache. No firmware or network terminal is loaded here.
prepare_dir="$root/.local/bluetooth-air-results"
printf 'include @%s\nmach create "air-cache"\nmachine LoadPlatformDescription @%s\nlog "BW_AIR_PLATFORM_PREPARED"\nquit\n' \
    "$root/simulation/renode/SpikePrimeDevices.cs" \
    "$root/simulation/renode/spike-prime-custom-dma.repl" > "$prepare_dir/prepare.resc"
timeout 120s "$renode_dir/renode" --disable-gui --console --plain \
    "$prepare_dir/prepare.resc" </dev/null > "$prepare_dir/prepare.log" 2>&1
grep -q 'BW_AIR_PLATFORM_PREPARED' "$prepare_dir/prepare.log"
# Renode's terminal API binds IPAddress.Any. Keep all three peer runs in
# ephemeral namespaces with only loopback, without altering the host network.
runner_user=$(id -un)
net_launcher=(unshare --net)
if [[ $(id -u) != 0 ]]; then
    net_launcher=(sudo --non-interactive unshare --net)
fi
for mode in le scratch classic; do
    case "$mode" in
        le) options=(--reconnect --periodic) ;;
        scratch) options=(--scratch-link 20131) ;;
        classic) options=(--classic --skip-le) ;;
    esac
    timeout 900s "${net_launcher[@]}" /bin/bash -c '
        set -euo pipefail
        ip link set lo up
        air_user=$1
        air_path=$2
        air_dotnet=$3
        shift 3
        exec runuser -u "$air_user" -- env "PATH=$air_path" "DOTNET_ROOT=$air_dotnet" "$@"
    ' bw-air-netns "$runner_user" "$PATH" "${DOTNET_ROOT:-}" \
        "$venv_dir/bin/python" "$root/simulation/bluetooth-air/test_spike_air.py" \
        --renode "$renode_dir" --air-tools "$air_tools" --images "$images" \
        --existing-filesystem "$fixture" \
        --workdir "$root/.local/bluetooth-air-results/$mode" "${options[@]}"
done
