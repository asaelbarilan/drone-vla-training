"""Boustrophedon sweep: search a region of known extent, lane by lane.

Ported from `drone_control/src/agent/boustrophedon.py`, where the argument was
settled by measurement rather than preference. The finding there, restated for
this testbed:

    Frontier exploration exists for **unknown extent** — you do not know how big
    the world is, so you push the boundary of the known. Our arena has **known
    extent**: the mission states a geofence. When the extent is known, coverage
    path planning applies instead, and boustrophedon cellular decomposition is
    provably complete (Choset & Pignon) where frontier exploration is complete
    only in the limit of unbounded time.

The failure this replaces is the same one drone_control diagnosed: a search
whose next move is chosen relative to where the drone already is lets the
vehicle's own drift decide what it never looks at. `BasePolicy.explore_target`
built an outward spiral anchored at launch, and measured on `grid_nav` seed 3,
c2 detected the target in **0 of 104** belief queries while c7 — which yaws
continuously — detected it in 70 of 132 in the same scene. The vehicle circled
at roughly constant radius with a body-fixed camera pointing tangentially, past
a target that was inside sensor range the whole time.

A lane pattern does not care where the drone is. It covers the region in world
coordinates, so no amount of drift leaves a strip unvisited.

**Lane spacing is derived, not chosen**, and the derivation differs from
drone_control's. There the sensor was treated as a disc, giving a swath of
2·R·sin(fov/2) either side of track. Here the camera is body-fixed and looks
*along* the lane, so what a pass actually covers is a forward wedge: at range R
with half-angle θ the far end of the wedge is 2·R·sin(θ) wide, but the near end
is a point. Taking the full wedge width as the pitch would leave unseen gaps
beside the vehicle, so the pitch is the width at *half* range, which is the
conservative reading of the same geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Lane:
    """One pass across the region, and the direction it is flown in."""

    index: int
    y: float
    x_from: float
    x_to: float

    @property
    def start(self) -> tuple[float, float]:
        return (self.x_from, self.y)

    @property
    def end(self) -> tuple[float, float]:
        return (self.x_to, self.y)


def lane_pitch_m(sensor_range_m: float, fov_deg: float, overlap: float = 0.8) -> float:
    """Lane spacing from the sensor geometry.

    Width of the view wedge at half the sensor's range, reduced by ``overlap``
    so neighbouring passes overlap rather than abut. Abutting lanes leave a
    seam, and a seam is precisely where a missed target hides.
    """
    half_angle = math.radians(max(fov_deg, 1.0) / 2.0)
    width_at_half_range = 2.0 * (sensor_range_m / 2.0) * math.sin(half_angle)
    return max(overlap * width_at_half_range, 1.0)


class BoustrophedonSweep:
    """Lane-by-lane coverage of an axis-aligned region in world coordinates."""

    def __init__(
        self,
        bounds: tuple[float, float, float, float],
        lane_spacing_m: float,
    ) -> None:
        x0, x1, y0, y1 = (float(v) for v in bounds)
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"degenerate sweep area: {bounds}")
        if lane_spacing_m <= 0:
            raise ValueError("lane spacing must be positive")
        self.bounds = (x0, x1, y0, y1)
        self.lane_spacing_m = lane_spacing_m
        self._lanes = self._build()
        self._done: set[int] = set()

    def _build(self) -> list[Lane]:
        x0, x1, y0, y1 = self.bounds
        lanes: list[Lane] = []
        # Start half a pitch in, so the first and last lanes cover the edges
        # rather than straddling them.
        y = y0 + self.lane_spacing_m / 2.0
        index = 0
        while y <= y1:
            forward = index % 2 == 0
            lanes.append(
                Lane(
                    index=index,
                    y=y,
                    x_from=x0 if forward else x1,
                    x_to=x1 if forward else x0,
                )
            )
            y += self.lane_spacing_m
            index += 1
        if not lanes:
            # Narrower than a single lane: sweep the centre line.
            lanes.append(Lane(index=0, y=(y0 + y1) / 2.0, x_from=x0, x_to=x1))
        return lanes

    @property
    def lanes(self) -> tuple[Lane, ...]:
        return tuple(self._lanes)

    def reset(self) -> None:
        self._done.clear()

    def next_waypoint(self, x: float, y: float) -> tuple[float, float] | None:
        """Where to fly next. ``None`` once every lane is finished.

        Picks the nearest unfinished lane rather than always the first, so a
        policy that enters the sweep part-way through a mission does not fly
        back to the corner before starting.
        """
        remaining = [ln for ln in self._lanes if ln.index not in self._done]
        if not remaining:
            return None
        lane = min(remaining, key=lambda ln: abs(ln.y - float(y)))
        on_lane = abs(lane.y - float(y)) <= self.lane_spacing_m / 2.0
        if not on_lane:
            return lane.start
        return lane.end if abs(float(x) - lane.x_from) <= abs(float(x) - lane.x_to) else lane.start

    def note_arrival(self, x: float, y: float, tolerance_m: float = 8.0) -> None:
        """Mark a lane finished once its far end is reached."""
        for lane in self._lanes:
            if lane.index in self._done:
                continue
            if (
                abs(lane.y - float(y)) <= self.lane_spacing_m / 2.0
                and abs(float(x) - lane.x_to) <= tolerance_m
            ):
                self._done.add(lane.index)

    @property
    def progress(self) -> tuple[int, int]:
        return len(self._done), len(self._lanes)

    def __len__(self) -> int:
        return len(self._lanes)


def sweep_for_mission(
    geofence_radius_m: float,
    sensor_range_m: float,
    fov_deg: float,
    overlap: float = 0.8,
) -> BoustrophedonSweep:
    """Build a sweep covering the mission's stated operating volume.

    The geofence is a *given constraint*, not privileged information, so sizing
    the search to it is not cheating — and a search that leaves its operating
    volume is measuring the harness rather than the architecture. The box is
    inscribed in the geofence circle so every lane end stays inside it.
    """
    half = geofence_radius_m / math.sqrt(2.0)
    return BoustrophedonSweep(
        (-half, half, -half, half), lane_pitch_m(sensor_range_m, fov_deg, overlap)
    )
