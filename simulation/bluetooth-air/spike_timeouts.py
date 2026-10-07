# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Bound host observation time separately from the guest's notification rate."""
import math


def le_round_trip_budget(periodic=False, reconnect_quiet=None):
    if not periodic:
        return 180
    if reconnect_quiet is None:
        return 300
    if not math.isfinite(reconnect_quiet) or reconnect_quiet < 0:
        raise ValueError("Reconnect observation window must be finite and nonnegative")
    # Reconnection observes silence before subscribing. That measured window
    # is additional to the ordinary subscribe/unsubscribe comparison budget.
    # The caller's overall scenario timeout still bounds the complete run.
    return 300 + min(300, reconnect_quiet)
