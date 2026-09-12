"""Ground-truth episode status reported by an environment adapter.

This is the scoring channel.  It never flows into a policy — only into the
orchestrator's termination logic and the metrics pipeline — which is what keeps
"did the agent succeed" independent of "what the agent believed".
"""

from __future__ import annotations

from pydantic import Field

from uavlab.contracts.common import StrictModel, TerminationReason, Vec3


class EnvironmentStatus(StrictModel):
    """Privileged truth about the current episode."""

    t_sim_ns: int
    position: Vec3
    distance_to_goal_m: float
    goal_visible: bool = False
    subgoals_completed: int = 0
    subgoals_total: int = 0
    task_complete: bool | None = None
    """Evaluator-only task gate. None preserves legacy point-goal scoring."""

    collided: bool = False
    collision_count: int = 0
    min_obstacle_distance_m: float = float("inf")
    out_of_bounds: bool = False
    constraint_violations: int = 0

    path_length_m: float = 0.0
    shortest_path_m: float = 0.0
    """Used for SPL; measured once at reset from the true start/goal geometry."""
    speed_mps: float = 0.0

    terminated: bool = False
    termination_reason: TerminationReason | None = None
    extras: dict[str, float] = Field(default_factory=dict)

    @property
    def within_goal(self) -> bool:
        return self.distance_to_goal_m <= self.extras.get("goal_radius_m", 2.0)
