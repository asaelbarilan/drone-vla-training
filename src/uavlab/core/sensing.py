"""Shared reading of the geometric sensing channel.

Both the planner and the safety shield ask the same question — "how much room
is there if I go that way?" — and they must answer it identically.  If they
disagreed, a plan the planner considered safe could be vetoed on every tick by
the shield, and the resulting intervention rate would be an artefact of two
inconsistent geometry readers rather than a property of the architecture.

The important detail is the angular window.  A depth fan is discrete; sampling
the single nearest ray means an obstacle sitting between two rays is invisible.
At a 24-ray fan that gap is 15 degrees, which is over two metres of unseen width
at ten metres range — easily enough to fly into.  So clearance is always the
*minimum* over a window around the direction of travel, never a single sample.
"""

from __future__ import annotations

import math

from uavlab.contracts import ObservationPacket

DEFAULT_HALF_WIDTH_RAD = math.radians(22.0)


def wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def min_clearance(
    obs: ObservationPacket,
    world_bearing: float,
    half_width_rad: float = DEFAULT_HALF_WIDTH_RAD,
) -> float:
    """Smallest range within ``half_width_rad`` of ``world_bearing``."""
    if not obs.range_rays:
        return obs.free_range_m
    body_bearing = wrap(world_bearing - obs.yaw_rad)
    best = float("inf")
    for bearing, distance in zip(obs.ray_bearings_rad, obs.range_rays, strict=True):
        if abs(wrap(bearing - body_bearing)) <= half_width_rad:
            best = min(best, distance)
    if best == float("inf"):
        # Window narrower than the ray spacing: fall back to the nearest ray so
        # the caller still gets a real reading rather than "infinitely clear".
        idx = min(
            range(len(obs.ray_bearings_rad)),
            key=lambda i: abs(wrap(obs.ray_bearings_rad[i] - body_bearing)),
        )
        return obs.range_rays[idx]
    return best


def widest_free_bearing(
    obs: ObservationPacket,
    desired_world_bearing: float,
    required_clearance_m: float,
    max_deflection_rad: float,
    step_rad: float,
    half_width_rad: float = DEFAULT_HALF_WIDTH_RAD,
) -> float | None:
    """Smallest deflection from ``desired_world_bearing`` that has room.

    Returns ``None`` when nothing within the deflection limit is clear, which
    the caller must treat as infeasible rather than papering over — an
    unexecutable plan has to be visible in the executable-plan rate.
    """
    offset = 0.0
    while offset <= max_deflection_rad:
        for sign in (1.0, -1.0) if offset > 0.0 else (1.0,):
            candidate = desired_world_bearing + sign * offset
            if min_clearance(obs, candidate, half_width_rad) >= required_clearance_m:
                return candidate
        offset += step_rad
    return None
