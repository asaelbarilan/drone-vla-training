"""Public mission evidence; never reads simulator scoring/goal state."""

from __future__ import annotations

import math
import re

from uavlab.contracts import MissionSpec, Vec3

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_COORDINATE = re.compile(
    rf"world ENU coordinate\s*\(\s*({_NUMBER})\s*,\s*({_NUMBER})\s*,\s*({_NUMBER})\s*\)",
    re.IGNORECASE,
)


def public_coordinate_goal(mission: MissionSpec) -> Vec3 | None:
    """Read the explicit coordinate contract of known-goal tasks only.

    This validates arrival, not action selection. The model still chooses goto
    and done. Ambiguous/missing coordinates cannot authorize a terminal stop.
    """
    if mission.task_family.value != "known_goal_nav":
        return None
    matches = _COORDINATE.findall(mission.instruction)
    if len(matches) != 1:
        return None
    values = [float(v) for v in matches[0]]
    if not all(math.isfinite(v) for v in values):
        return None
    return Vec3(x=values[0], y=values[1], z=values[2])
