"""Public mission evidence; never reads simulator scoring/goal state."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

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


@dataclass(frozen=True, slots=True)
class OrderedVisitContract:
    first: str
    second: str
    radius_m: float
    final_radius_m: float
    dwell_s: float = 0.5


def public_ordered_visit(mission: MissionSpec) -> OrderedVisitContract | None:
    """Recognize this explicit public two-object task; never infer an unseen goal."""
    if mission.task_family.value != "multi_stage":
        return None
    text = " ".join(mission.instruction.split())
    match = re.fullmatch(
        rf"Visit the ([a-z ]+) first, staying within ({_NUMBER}) metres for at least "
        rf"half a second, then visit the ([a-z ]+) and stop within ({_NUMBER}) metres\.",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    first, radius, second, final_radius = match.groups()
    a, b = float(radius), float(final_radius)
    if first.casefold() == second.casefold() or not all(math.isfinite(x) and x > 0 for x in (a, b)):
        return None
    return OrderedVisitContract(first.casefold(), second.casefold(), a, b)


@dataclass(slots=True)
class OrderedVisitEvidence:
    """Onboard object locations and observed dwell; contains no simulator result."""

    contract: OrderedVisitContract
    locations: dict[str, tuple[Vec3, int]] = field(default_factory=dict)
    first_completed_t_ns: int | None = None
    inside_since_ns: int | None = None
    last_observation_seq: int = -1
    last_t_ns: int = -1
    max_location_age_s: float = 30.0

    def locate(self, label: str, position: Vec3, source_t_ns: int):
        old = self.locations.get(label)
        if label == self.contract.first and old and old[0].distance_to(position) > 0.1:
            self.inside_since_ns = None
        self.locations[label] = (position, source_t_ns)

    def location(self, label: str, t_ns: int):
        item = self.locations.get(label)
        if item and 0 <= t_ns - item[1] <= self.max_location_age_s * 1e9:
            return item[0]
        return None

    def observe(self, obs):
        if obs.seq <= self.last_observation_seq or obs.t_sim_ns <= self.last_t_ns:
            return
        previous_t = self.last_t_ns
        self.last_observation_seq, self.last_t_ns = obs.seq, obs.t_sim_ns
        if self.first_completed_t_ns is not None:
            return
        location = self.location(self.contract.first, obs.t_sim_ns)
        near = location is not None and obs.position.distance_to(location) <= self.contract.radius_m
        # Missing observation intervals cannot fabricate continuous dwell.
        if not near or obs.t_sim_ns - previous_t > 100_000_000:
            self.inside_since_ns = obs.t_sim_ns if near else None
        elif self.inside_since_ns is None:
            self.inside_since_ns = obs.t_sim_ns
        if (
            self.inside_since_ns is not None
            and obs.t_sim_ns - self.inside_since_ns >= self.contract.dwell_s * 1e9
        ):
            self.first_completed_t_ns = obs.t_sim_ns

    def stop_supported(self, obs):
        location = self.location(self.contract.second, obs.t_sim_ns)
        return (
            self.first_completed_t_ns is not None
            and obs.t_sim_ns >= self.first_completed_t_ns
            and location is not None
            and obs.position.distance_to(location) <= self.contract.final_radius_m
            and obs.velocity.norm() <= 0.75
        )
