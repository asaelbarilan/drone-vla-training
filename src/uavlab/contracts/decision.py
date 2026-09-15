"""The DecisionEnvelope — the single most important contract in the testbed.

Every semantic output, from any model, is normalised into this small
discriminated union before it can influence motion.  Three properties follow
directly and are the reason the comparison is fair at all:

* one safety logger observes every architecture identically;
* latency is measurable from observation to executed decision, not just model
  inference time;
* raw model text can never reach a controller, because the controller only
  accepts a typed payload.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from uavlab.contracts.common import DecisionKind, ProgressLabel, StrictModel, Vec3


class SkillCall(StrictModel):
    """Bounded call into a predefined skill vocabulary (TypeFly/AerialClaw-like)."""

    kind: Literal[DecisionKind.SKILL] = DecisionKind.SKILL
    skill_name: str
    args: dict[str, float | str | bool] = Field(default_factory=dict)


class WaypointGoal(StrictModel):
    """A semantic goal position for a classical planner (SPF/OnFly-like)."""

    kind: Literal[DecisionKind.WAYPOINT] = DecisionKind.WAYPOINT
    target: Vec3
    target_label: str | None = None
    tolerance_m: float = 1.0
    stop_at_target: bool = False
    """Explicit terminal intent, so arrived and stopped stay distinguishable."""
    view_yaw_rad: float | None = Field(default=None, allow_inf_nan=False)
    """Optional camera heading at this waypoint, not a terminal mission stop."""


class KinematicAction(StrictModel):
    """One learned action step (CognitiveDrone/AeroVLA-like).

    The representation is frozen for a whole matched experiment: a velocity VLA
    is never compared against a collision-checked position target and called an
    architecture-only comparison.
    """

    kind: Literal[DecisionKind.KINEMATIC_ACTION] = DecisionKind.KINEMATIC_ACTION
    velocity: Vec3
    yaw_rate_rps: float = 0.0
    duration_s: float = 0.1


class ActionChunk(StrictModel):
    """A short receding-horizon sequence of learned actions (FLIGHT/ScoutVLA-like)."""

    kind: Literal[DecisionKind.ACTION_CHUNK] = DecisionKind.ACTION_CHUNK
    actions: tuple[KinematicAction, ...]
    replan_after: int | None = None
    """Execute at most this many steps before requiring a fresh inference."""

    @model_validator(mode="after")
    def _non_empty(self) -> ActionChunk:
        if not self.actions:
            raise ValueError("ActionChunk must contain at least one action")
        return self


class MissionDirective(StrictModel):
    """Supervisory output with no motor authority whatsoever.

    A monitor's CONTINUE/STOP/LOST verdict and a slow reasoner's subgoal both
    land here.  The decision router will refuse to hand this to a controller.
    """

    kind: Literal[DecisionKind.MISSION_DIRECTIVE] = DecisionKind.MISSION_DIRECTIVE
    label: ProgressLabel
    subgoal: str | None = None
    target_hint: Vec3 | None = None
    rationale: str | None = None


DecisionPayload = Annotated[
    Union[SkillCall, WaypointGoal, KinematicAction, ActionChunk, MissionDirective],
    Field(discriminator="kind"),
]


class DecisionEnvelope(StrictModel):
    """A typed semantic output with full provenance and timing."""

    decision_id: str
    kind: DecisionKind
    payload: DecisionPayload

    source_observation_seq: int
    source_t_sim_ns: int
    """Sim time of the observation this decision was computed from."""
    produced_t_wall_ns: int
    produced_t_sim_ns: int
    valid_until_t_sim_ns: int | None = None
    """Hard expiry.  ``None`` means "no self-declared expiry"; the router still
    applies the architecture-wide staleness bound."""

    confidence: float | None = None
    producer: str = "unknown"
    """Plugin name, for attributing rejections to the component that caused them."""
    provenance: dict[str, str] = Field(default_factory=dict)
    """Model id, prompt hash, trigger reason.  Never free-form model output."""

    @model_validator(mode="after")
    def _kind_matches_payload(self) -> DecisionEnvelope:
        if self.payload.kind is not self.kind:
            raise ValueError(
                f"envelope kind {self.kind.value!r} disagrees with payload "
                f"{self.payload.kind.value!r}"
            )
        return self

    def age_ns(self, execution_t_sim_ns: int) -> int:
        """Decision staleness: how obsolete the world was at execution time.

        This is the metric that separates "slow but still valid" from "slow and
        computed from a frame several metres ago", and it is the reason
        asynchronous architectures need more than an inference-latency number.
        """
        return execution_t_sim_ns - self.source_t_sim_ns

    def is_expired(self, t_sim_ns: int) -> bool:
        return self.valid_until_t_sim_ns is not None and t_sim_ns > self.valid_until_t_sim_ns
