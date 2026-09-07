#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Structural locks for the non-destructive LEGO sensor snapshot ABI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "boards/spike-prime-hub/include/board_legosensor.h").read_text()
SOURCE = (ROOT / "boards/spike-prime-hub/src/legosensor_uorb.c").read_text()


def require(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise SystemExit(f"missing structural contract: {needle}")


require(HEADER, "#define LEGOSENSOR_GET_LATEST        _SNIOC(0x00f8)")
require(HEADER, "It returns `-ENODATA`")
require(SOURCE, "p->latest = sample;")
require(SOURCE, "p->latest_valid = true;")
require(SOURCE, "case LEGOSENSOR_GET_LATEST:")
require(SOURCE, "cs->bind_generation != bind_generation")
require(SOURCE, "ret = -EAGAIN;")
require(SOURCE, "ret = -ENODATA;")

case = SOURCE.split("case LEGOSENSOR_GET_LATEST:", 1)[1].split(
    "case LEGOSENSOR_CLAIM:", 1
)[0]
require(case, "board_user_out_ok(out, sizeof(*out))")
require(case, "sample = p->latest;")
if "read(" in case or "POLL_DATA" in case or "push_event" in case:
    raise SystemExit("GET_LATEST must not consume or publish stream data")

print("legosensor latest-frame structural checks passed")
