"""Trajectory and control contracts — the controller-independence boundary."""

from __future__ import annotations

from pydantic import Field, model_validator

from uavlab.contracts.common import Frame, StrictModel, Vec3


class TrajectoryPoint(StrictModel):
    t_offset_ns: int
    position: Vec3
    velocity: Vec3 | None = None
    yaw_rad: float | None = None


class Trajectory(StrictModel):
    """The common waypoint-to-planner handoff."""

    start_t_sim_ns: int
    points: tuple[TrajectoryPoint, ...]
    source_decision_id: str | None = None
    planner_name: str = "unknown"
    feasible: bool = True
    reason: str | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> Trajectory:
        if self.feasible and not self.points:
            raise ValueError("a feasible Trajectory must contain at least one point")
        return self


class ControlCommand(StrictModel):
    """The one canonical control representation for the whole benchmark.

    Every architecture ends here, whatever its semantic authority, so that a
    skill agent and a direct VLA are physically comparable.  ``expires_t_sim_ns``
    lets the environment refuse to keep flying on a command whose author has
    gone silent.
    """

    t_sim_ns: int
    velocity: Vec3
    yaw_rate_rps: float = 0.0
    frame: Frame = Frame.ENU
    expires_t_sim_ns: int | None = None

    source_decision_id: str | None = None
    source_observation_seq: int | None = None
    source_t_sim_ns: int | None = None
    """Observation time behind this command; ``decision_age`` is derived from it."""
    safety_modified: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def is_hold(self) -> bool:
        return self.velocity.norm() < 1e-9 and abs(self.yaw_rate_rps) < 1e-9

    def decision_age_ns(self, execution_t_sim_ns: int) -> int | None:
        if self.source_t_sim_ns is None:
            return None
        return execution_t_sim_ns - self.source_t_sim_ns
