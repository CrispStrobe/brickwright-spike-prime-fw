# SPDX-License-Identifier: Apache-2.0
"""The legacy (SPIKE 2.x) JSON requests Brickwright lite sends over Classic.

`methods_in_extension` derives the set from lite's extension source
(overlay/scratch-vm/src/extensions/crispstrobe/spikeprime/index.js): every
string literal passed as the first argument of a `sendCommand(` call. Case
labels (the SPIKE 3 tunnel's switch) are not call sites and are not counted.

`REQUESTS` holds one request per method, with the parameter object built the
way the extension builds it (same keys, same order, lite's defaults: speed 50,
stop mode brake = 1, stall detection on). The air test sends each with an
added request id so the reply is observable; lite itself omits the id.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REQUESTS = {
    "trigger_current_state": {},
    "scratch.motor_run_for_degrees":
        {"port": "A", "speed": 50, "degrees": 360, "stop": 1, "stall": True},
    "scratch.motor_run_timed":
        {"port": "A", "speed": 50, "time": 1000, "stop": 1, "stall": True},
    "scratch.motor_start": {"port": "A", "speed": 50, "stall": True},
    "scratch.motor_stop": {"port": "A", "stop": 1},
    "scratch.display_text": {"text": "Hi"},
    "scratch.display_clear": {},
    "scratch.display_set_pixel": {"x": 2, "y": 2, "brightness": 9},
    "scratch.center_button_lights": {"color": 9},
    "scratch.sound_beep": {"frequency": 440, "duration": 200},
}


def extension_source(path: Path) -> str:
    """Lite ships the extension as makeExt("<source as a JSON string>")."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r'makeExt\((".*")\)\s*;?\s*$', text, re.S)
    return json.loads(match.group(1)) if match else text


def methods_in_extension(path: Path) -> set[str]:
    source = extension_source(path)
    return set(re.findall(r'sendCommand\(\s*"([A-Za-z_.]+)"', source))


def request_line(method: str, request_id: str) -> bytes:
    # JSON.stringify output (no spaces) followed by "\r", as sendJSON does.
    body = {"i": request_id, "m": method, "p": REQUESTS[method]}
    return (json.dumps(body, separators=(",", ":")) + "\r").encode()
