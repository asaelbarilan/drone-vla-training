"""Mission definition — identical across every architecture under test."""

from __future__ import annotations

from pydantic import Field

from uavlab.contracts.common import StrictModel, TaskFamily, Vec3


class SuccessCriteria(StrictModel):
    """How an episode is scored.

    The criteria live in the mission, not in the environment adapter and not in
    the architecture, so that the same yardstick applies to a skill agent and a
    direct VLA.
    """

    goal_radius_m: float = 2.0
    require_terminal_stop: bool = True
    """If true, reaching the goal is not enough; the agent must also *stop*.

    This is what separates "flew past the target" from "completed the mission",
    and it is the metric OnFly-style monitors are supposed to improve.
    """
    max_flight_time_s: float = 120.0
    required_subgoals: int = 0
    """Number of ordered subgoals that must be visited before the final goal."""


class MissionConstraints(StrictModel):
    """Hard physical limits every architecture must respect."""

    max_speed_mps: float = 5.0
    max_accel_mps2: float = 4.0
    min_altitude_m: float = 0.5
    max_altitude_m: float = 30.0
    geofence_radius_m: float = 100.0
    min_obstacle_clearance_m: float = 0.6


class MissionSpec(StrictModel):
    """The task, stated once, in architecture-neutral terms."""

    mission_id: str
    instruction: str
    """Free-form natural-language instruction, e.g. "fly to the red tower"."""
    task_family: TaskFamily
    success: SuccessCriteria = Field(default_factory=SuccessCriteria)
    constraints: MissionConstraints = Field(default_factory=MissionConstraints)

    start_pose: Vec3 | None = None
    goal_hint: Vec3 | None = None
    """Coarse goal hint when the regime provides one.

    ``None`` in the object-search regime, where the target must be found.  A
    policy that reads this field in a search episode is cheating, and the
    orchestrator will not populate it.
    """
    allowed_skills: tuple[str, ...] = ()
    """Bounded skill vocabulary.  Empty means "no skill authority in this run"."""
    metadata: dict[str, str] = Field(default_factory=dict)
