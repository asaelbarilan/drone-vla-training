"""Recovery and slow-reasoner plugins.

The same component fills two architecturally different slots, and that is
deliberate:

* scheduled **periodically or asynchronously**, it is a slow semantic reasoner
  running beside a fast executor (the hierarchical fast/slow family);
* scheduled by a **trigger**, it is a recovery reasoner that is absent during
  nominal execution and admitted only when the mission stops progressing (the
  selective-invocation family).

Holding the component fixed and changing only the admission policy is what makes
those two competing hypotheses comparable.  If the reasoner itself changed too,
any difference would be uninterpretable.

What it may emit is bounded by ``emit``, because a recovery output has to be
routable under the architecture's authority: a directive for a direct-VLA stack,
a waypoint or a skill where a planner or a skill runtime exists to receive it.
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    MissionDirective,
    MissionSpec,
    ProgressLabel,
    RecoveryRequest,
    SkillCall,
    Vec3,
    WaypointGoal,
    s_to_ns,
)
from uavlab.core.registry import register
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import DecisionContext, InferenceRequest
from uavlab.plugins.reasoning.base import recall_target

EMIT_KINDS = ("directive", "waypoint", "skill")


@register("recovery", "bounded_reasoner")
class BoundedRecoveryReasoner:
    """Expensive semantic reasoning, bounded in output and in budget."""

    def __init__(self, **params: Any) -> None:
        self.model_id = str(params.get("model_id", "sim-reasoner"))
        self.emit = str(params.get("emit", "directive"))
        if self.emit not in EMIT_KINDS:
            raise ValueError(f"recovery emit must be one of {EMIT_KINDS}, got {self.emit!r}")
        self.target_label = str(params.get("target_label", "target"))
        self.detour_m = float(params.get("detour_m", 8.0))
        self.search_radius_m = float(params.get("search_radius_m", 12.0))
        self.validity_s = float(params.get("validity_s", 4.0))
        self.stall_threshold_s = float(params.get("stall_threshold_s", 2.0))
        self.uncertainty_threshold = float(params.get("uncertainty_threshold", 0.6))
        self.allowed_skills = tuple(params.get("allowed_skills", ("back_off", "ascend", "scan")))

        self.services: RuntimeServices | None = None
        self.calls = 0
        self._search_phase = 0.0

    @property
    def name(self) -> str:
        return "bounded_reasoner"

    def bind_runtime(self, services: RuntimeServices) -> None:
        self.services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self.calls = 0
        self._search_phase = 0.0

    async def recover(
        self, request: RecoveryRequest, ctx: DecisionContext
    ) -> DecisionEnvelope | None:
        if self.services is not None and self.services.inference is not None:
            await self.services.inference.invoke(
                InferenceRequest(
                    model_id=self.model_id,
                    role="reasoner",
                    prompt_hash=f"recovery:{request.trigger.observation_seq}",
                    input_tokens=192 + len(request.state_summary) // 4,
                    image_count=1,
                    observation_seq=request.trigger.observation_seq,
                )
            )
        self.calls += 1

        situation = self._diagnose(ctx)
        target = self._propose_target(ctx, situation)

        match self.emit:
            case "directive":
                payload = MissionDirective(
                    label=self._label_for(situation),
                    subgoal=situation,
                    target_hint=target,
                    rationale=f"{situation}: {request.trigger.cause}",
                )
                kind = DecisionKind.MISSION_DIRECTIVE
            case "waypoint":
                payload = WaypointGoal(
                    target=target or ctx.observation.position,
                    target_label=self.target_label,
                    tolerance_m=2.0,
                    stop_at_target=False,
                )
                kind = DecisionKind.WAYPOINT
            case _:
                payload = self._skill_for(situation, ctx)
                kind = DecisionKind.SKILL

        now_ns = self.services.clock.now_ns() if self.services else ctx.t_sim_ns
        wall_ns = self.services.clock.wall_ns() if self.services else ctx.t_wall_ns
        return DecisionEnvelope(
            decision_id=uuid.uuid4().hex[:12],
            kind=kind,
            payload=payload,
            source_observation_seq=request.trigger.observation_seq,
            source_t_sim_ns=ctx.observation.t_sim_ns,
            produced_t_wall_ns=wall_ns,
            produced_t_sim_ns=now_ns,
            valid_until_t_sim_ns=now_ns + s_to_ns(self.validity_s),
            confidence=0.75,
            producer=self.name,
            provenance={
                "model_id": self.model_id,
                "trigger": request.trigger.name,
                "cause": request.trigger.cause,
                "call_index": str(request.call_index),
            },
        )

    # -- reasoning ----------------------------------------------------------

    def _diagnose(self, ctx: DecisionContext) -> str:
        """Name the situation. The label is what makes recovery auditable."""
        progress = ctx.last_progress
        geometry = ctx.perception.geometry
        clearance = geometry.free_radius_m if geometry else float("inf")

        if progress is not None and progress.label is ProgressLabel.BLOCKED:
            return "blocked"
        if clearance < 2.0:
            return "blocked"
        if progress is not None and progress.label is ProgressLabel.AMBIGUOUS:
            return "ambiguous_target"
        if ctx.perception.uncertainty >= self.uncertainty_threshold and not ctx.perception.detections:
            return "target_lost"
        if progress is not None and progress.stalled_for_s >= self.stall_threshold_s:
            return "no_progress"
        return "nominal"

    def _label_for(self, situation: str) -> ProgressLabel:
        return {
            "blocked": ProgressLabel.BLOCKED,
            "target_lost": ProgressLabel.LOST,
            "ambiguous_target": ProgressLabel.AMBIGUOUS,
            "no_progress": ProgressLabel.CONTINUE,
            "nominal": ProgressLabel.CONTINUE,
        }[situation]

    def _propose_target(self, ctx: DecisionContext, situation: str) -> Vec3 | None:
        """Choose where to go next, using memory the executor may not have."""
        remembered = recall_target(ctx, self.target_label)
        best_detection = max(
            (d for d in ctx.perception.detections if d.label == self.target_label and d.position),
            key=lambda d: d.score,
            default=None,
        )
        position = ctx.observation.position

        if situation == "blocked":
            # Sidestep perpendicular to the blocked heading rather than retrying
            # the same line, which is what "no progress" usually means.
            anchor = (
                best_detection.position
                if best_detection and best_detection.position
                else (remembered.position if remembered else None)
            )
            bearing = (
                math.atan2(anchor.y - position.y, anchor.x - position.x)
                if anchor
                else ctx.observation.yaw_rad
            )
            side = bearing + math.pi / 2.0
            return Vec3(
                x=position.x + self.detour_m * math.cos(side),
                y=position.y + self.detour_m * math.sin(side),
                z=min(position.z + 2.0, 20.0),
            )

        if best_detection is not None and best_detection.position is not None:
            return best_detection.position
        if remembered is not None and remembered.position is not None:
            return remembered.position

        self._search_phase += math.radians(72.0)
        return Vec3(
            x=position.x + self.search_radius_m * math.cos(self._search_phase),
            y=position.y + self.search_radius_m * math.sin(self._search_phase),
            z=position.z,
        )

    def _skill_for(self, situation: str, ctx: DecisionContext) -> SkillCall:
        if situation == "blocked" and "back_off" in self.allowed_skills:
            return SkillCall(skill_name="back_off", args={"distance_m": 3.0})
        if situation in ("target_lost", "ambiguous_target") and "scan" in self.allowed_skills:
            return SkillCall(skill_name="scan", args={"yaw_rate_rps": 0.9, "duration_s": 1.5})
        if "ascend" in self.allowed_skills:
            return SkillCall(skill_name="ascend", args={"dz": 2.0})
        return SkillCall(skill_name="hover")

    def stats(self) -> dict[str, float]:
        return {"recovery_calls": float(self.calls)}


@register("recovery", "hierarchical_reasoner")
class HierarchicalReasoner(BoundedRecoveryReasoner):
    """The slow half of a fast/slow hierarchy.

    Identical machinery to the recovery reasoner — only the schedule differs.
    Keeping them the same class is what guarantees that a periodic-versus-
    triggered comparison is a comparison of *admission policy* and nothing else.
    """

    def __init__(self, **params: Any) -> None:
        params.setdefault("emit", "directive")
        super().__init__(**params)

    @property
    def name(self) -> str:
        return "hierarchical_reasoner"
