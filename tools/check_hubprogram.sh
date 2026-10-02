#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
output=$(mktemp -d)
trap 'rm -rf "$output"' EXIT HUP INT TERM
cd "$root"
python3 tools/check_reuse_licenses.py
cc -std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined apps/hubprogram/program.c apps/hubprogram/upload.c apps/hubprogram/test/program_test.c -o "$output/program"
"$output/program"
cc -std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined apps/hubprogram/program.c apps/hubprogram/upload.c apps/hubprogram/storage.c apps/hubprogram/test/storage_test.c -o "$output/storage"
"$output/storage"
cc -std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined apps/hubprogram/program.c apps/hubprogram/upload.c apps/hubprogram/test/service_test.c -pthread -o "$output/service"
"$output/service"
cc -std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined -Itests/hubprogram/include -Iboards/spike-prime-hub/include apps/hubprogram/motor.c tests/hubprogram/control_test.c -o "$output/control"
"$output/control"
mp=third_party/micropython-embed
cc -std=gnu99 -D_POSIX_C_SOURCE=200809L -Os -fno-common -Iapps/hubprogram/micropython -I"$mp" -I"$mp/port" "$mp"/py/*.c "$mp"/port/embed_util.c "$mp"/shared/runtime/gchelper_generic.c apps/hubprogram/micropython/brickwright_module.c apps/hubprogram/python_output.c apps/hubprogram/test/python_test.c -lm -o "$output/python"
"$output/python"
