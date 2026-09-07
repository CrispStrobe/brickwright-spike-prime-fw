#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail closed when the protected firmware exceeds reviewed resource bounds."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class BudgetError(RuntimeError):
    pass


def parse_size(output: str) -> tuple[int, int]:
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 4 and all(field.isdigit() for field in fields[:3]):
            text, data, bss = map(int, fields[:3])
            return text + data, data + bss
    raise BudgetError("could not parse text/data/bss from size output")


def parse_nm_symbol_size(output: str, symbol: str) -> int:
    # arm-none-eabi-nm -S emits: address size type name
    matches = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[-1] == symbol:
            try:
                matches.append(int(fields[-3], 16))
            except ValueError:
                continue
    if len(matches) != 1:
        raise BudgetError(f"expected exactly one {symbol} symbol, found {len(matches)}")
    return matches[0]


def parse_nm_symbol_value(output: str, symbol: str) -> int:
    matches = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[-1] == symbol:
            try:
                matches.append(int(fields[0], 16))
            except ValueError:
                continue
    if len(matches) != 1:
        raise BudgetError(f"expected exactly one {symbol} symbol, found {len(matches)}")
    return matches[0]


def parse_defines(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    patterns = (
        re.compile(r"^\s*#define\s+(CONFIG_[A-Z0-9_]+)\s+([0-9]+|0x[0-9a-fA-F]+)\s*$"),
        re.compile(r"^(CONFIG_[A-Z0-9_]+)=([0-9]+|0x[0-9a-fA-F]+)\s*$"),
    )
    for line in text.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                values[match.group(1)] = int(match.group(2), 0)
                break
    return values


def check_configuration(root: Path, configuration: dict) -> list[str]:
    report = []
    for relative, limits in configuration.items():
        path = root / relative
        if not path.is_file():
            raise BudgetError(f"required configuration is missing: {relative}")
        values = parse_defines(path.read_text(encoding="utf-8"))
        for name, bound in limits.items():
            if name not in values:
                raise BudgetError(f"{name} is missing from {relative}")
            value = values[name]
            if not bound["min"] <= value <= bound["max"]:
                raise BudgetError(
                    f"{name}={value} outside [{bound['min']}, {bound['max']}]"
                )
            report.append(f"{name}={value} [{bound['min']}, {bound['max']}]")
    return report


def run(arguments: argparse.Namespace) -> list[str]:
    root = arguments.root.resolve()
    policy = json.loads((root / arguments.policy).read_text(encoding="utf-8"))
    if policy.get("schema") != 1:
        raise BudgetError("unsupported resource-budget policy schema")
    target = policy["protected_userspace"]
    elf = root / arguments.elf
    if not elf.is_file():
        raise BudgetError(f"protected userspace ELF is missing: {arguments.elf}")

    size_output = subprocess.run(
        [arguments.size_tool, str(elf)], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    flash, static_ram = parse_size(size_output)
    if flash > target["flash_bytes_max"]:
        raise BudgetError(f"userspace flash {flash} exceeds {target['flash_bytes_max']}")
    if static_ram > target["static_ram_bytes_max"]:
        raise BudgetError(
            f"userspace static RAM {static_ram} exceeds {target['static_ram_bytes_max']}"
        )

    nm_output = subprocess.run(
        [arguments.nm_tool, "-S", str(elf)], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    payload_size = parse_nm_symbol_size(nm_output, target["ti_payload_symbol"])
    if payload_size != target["ti_payload_bytes_exact"]:
        raise BudgetError(
            f"synthetic TI footprint is {payload_size}, expected "
            f"{target['ti_payload_bytes_exact']}"
        )

    data_start = parse_nm_symbol_value(nm_output, "_sdata")
    pools_start = parse_nm_symbol_value(nm_output, "__start_net_buf_pool")
    pools_stop = parse_nm_symbol_value(nm_output, "__stop_net_buf_pool")
    data_stop = parse_nm_symbol_value(nm_output, "_edata")
    if not data_start <= pools_start < pools_stop <= data_stop:
        raise BudgetError(
            "net_buf_pool initializers are outside protected initialized data: "
            f"0x{data_start:x} <= 0x{pools_start:x} < 0x{pools_stop:x} "
            f"<= 0x{data_stop:x}"
        )

    report = [
        f"userspace flash={flash}/{target['flash_bytes_max']} bytes",
        f"userspace static_ram={static_ram}/{target['static_ram_bytes_max']} bytes",
        f"synthetic TI payload={payload_size} bytes (exact)",
        f"net_buf_pool=0x{pools_start:x}..0x{pools_stop:x} inside initialized data",
    ]
    report.extend(check_configuration(root, policy["configuration"]))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--policy", default="policy/resource-budgets.json")
    parser.add_argument("--elf", default="nuttx/nuttx_user.elf")
    parser.add_argument("--size-tool", default="arm-none-eabi-size")
    parser.add_argument("--nm-tool", default="arm-none-eabi-nm")
    arguments = parser.parse_args()
    try:
        for line in run(arguments):
            print(f"resource-budget: {line}")
    except (BudgetError, OSError, KeyError, json.JSONDecodeError,
            subprocess.CalledProcessError) as error:
        print(f"resource-budget: ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
