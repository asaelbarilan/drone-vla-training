"""Semantic policies, one per authority level.

Together with the schedulers and memories, these are what the sentinel
configurations recombine.  Read them as *stand-ins*: each reproduces the
information flow and the authority boundary of a published family, with a
simulated model in place of the real one, so that the runtime can be proved
modular before any checkpoint is downloaded.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from uavlab.contracts import (
    ActionChunk,
    DecisionEnvelope,
    DecisionKind,
    KinematicAction,
    MissionSpec,
    MissionDirective,
    ProgressLabel,
    SkillCall,
    Vec3,
    WaypointGoal,
)
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext
from uavlab.plugins.reasoning.base import BasePolicy, TargetBelief


def _unit_toward(origin: Vec3, target: Vec3) -> tuple[float, float, float]:
    dx, dy, dz = target.x - origin.x, target.y - origin.y, target.z - origin.z
    norm = math.sqrt(dx * dx + dy * dy + dz * dz)
    if norm < 1e-9:
        return (0.0, 0.0, 0.0)
    return (dx / norm, dy / norm, dz / norm)


# --------------------------------------------------------------------------
# Waypoint authority
# --------------------------------------------------------------------------


@register("policy", "oracle_waypoint")
class OracleWaypointPolicy(BasePolicy):
    """C0's control ceiling: perfect semantics, ordinary planner and controller.

    Its only job is to answer "how much failure is attributable to semantic
    architecture rather than to the flight stack?".  If this configuration
    cannot reach the goal, nothing measured about foundation-model architecture
    in the same environment means anything yet.
    """

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "oracle")
        super().__init__(**params)

    @property
    def name(self) -> str:
        return "oracle_waypoint"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("waypoint", "mission_directive")

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        await self.charge(ctx)
        belief = self.believe(ctx)
        if not belief.known:
            return None
        assert belief.position is not None
        distance = ctx.observation.position.distance_to(belief.position)
        if distance <= self.stop_radius_m and self.self_terminate:
            self._stopped = True
            return self.envelope(
                ctx,
                DecisionKind.MISSION_DIRECTIVE,
                MissionDirective(label=ProgressLabel.STOP, rationale="oracle: goal reached"),
                1.0,
            )
        return self.envelope(
            ctx,
            DecisionKind.WAYPOINT,
            WaypointGoal(
                target=belief.position,
                target_label=self.target_label,
                tolerance_m=1.0,
                stop_at_target=True,
            ),
            1.0,
        )


@register("policy", "vlm_waypoint")
class VLMWaypointPolicy(BasePolicy):
    """Semantic grounding to a waypoint, then a classical planner.

    The SPF/OnFly-shaped family.  Its competence is bounded by what it can see
    or remember, so its behaviour changes materially with the memory plugin
    underneath it — which is the point of the C4->C5 contrast.
    """

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "sim-vlm")
        super().__init__(**params)
        self.hop_m = float(params.get("hop_m", 12.0))
        """Waypoints are proposed at most this far ahead, like a real VLM hop."""

    @property
    def name(self) -> str:
        return "vlm_waypoint"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("waypoint", "mission_directive")

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        await self.charge(ctx)
        belief = self.believe(ctx)

        if self.should_stop(belief, ctx):
            self._stopped = True
            return self.envelope(
                ctx,
                DecisionKind.MISSION_DIRECTIVE,
                MissionDirective(
                    label=ProgressLabel.STOP,
                    rationale=f"believed arrival ({belief.source}, conf {belief.confidence:.2f})",
                ),
                belief.confidence,
            )

        if belief.known:
            assert belief.position is not None
            target = self._hop_toward(ctx.observation.position, belief.position)
            return self.envelope(
                ctx,
                DecisionKind.WAYPOINT,
                WaypointGoal(
                    target=target,
                    target_label=self.target_label,
                    tolerance_m=1.5,
                    stop_at_target=False,
                ),
                belief.confidence,
                note=belief.source,
            )

        return self.envelope(
            ctx,
            DecisionKind.WAYPOINT,
            WaypointGoal(target=self.explore_target(ctx), tolerance_m=2.5),
            0.1,
            note="exploration",
        )

    def _hop_toward(self, origin: Vec3, target: Vec3) -> Vec3:
        distance = origin.distance_to(target)
        if distance <= self.hop_m:
            return target
        ux, uy, uz = _unit_toward(origin, target)
        return Vec3(
            x=origin.x + ux * self.hop_m,
            y=origin.y + uy * self.hop_m,
            z=origin.z + uz * self.hop_m,
        )


@register("policy", "random_waypoint")
class RandomWaypointPolicy(BasePolicy):
    """A semantics-free control.

    Any architecture that cannot beat this is not being helped by its foundation
    model, and having the baseline in the same runtime makes that check cheap.
    """

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "random")
        super().__init__(**params)
        self.radius_m = float(params.get("radius_m", 10.0))
        self._rng = np.random.default_rng(0)

    @property
    def name(self) -> str:
        return "random_waypoint"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("waypoint",)

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self._rng = np.random.default_rng(seed + 31)

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        await self.charge(ctx)
        offset = self._rng.normal(0.0, self.radius_m, size=3)
        position = ctx.observation.position
        return self.envelope(
            ctx,
            DecisionKind.WAYPOINT,
            WaypointGoal(
                target=Vec3(
                    x=position.x + float(offset[0]),
                    y=position.y + float(offset[1]),
                    z=max(1.0, position.z + float(offset[2]) * 0.2),
                ),
                tolerance_m=2.0,
            ),
            0.0,
        )


# --------------------------------------------------------------------------
# Skill authority
# --------------------------------------------------------------------------


@register("policy", "scripted_skill")
class ScriptedSkillPolicy(BasePolicy):
    """Bounded skill selection from a compact program-like vocabulary.

    The TypeFly/AerialClaw-shaped family: the model never touches motion
    directly, it selects from a validated skill set, and everything else in the
    stack is unchanged.  That is what makes C1 a clean answer to "is coarse,
    bounded mission authority enough?".
    """

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "sim-llm")
        super().__init__(**params)
        self.standoff_m = float(params.get("standoff_m", 1.5))
        self.scan_when_lost = bool(params.get("scan_when_lost", True))
        self._lost_ticks = 0

    @property
    def name(self) -> str:
        return "scripted_skill"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("skill", "mission_directive")

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self._lost_ticks = 0

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        await self.charge(ctx)
        belief = self.believe(ctx)

        if self.should_stop(belief, ctx):
            self._stopped = True
            return self.envelope(
                ctx,
                DecisionKind.SKILL,
                SkillCall(skill_name="stop", args={"reason": "believed arrival"}),
                belief.confidence,
            )

        if belief.known:
            self._lost_ticks = 0
            assert belief.position is not None
            return self.envelope(
                ctx,
                DecisionKind.SKILL,
                SkillCall(
                    skill_name="goto",
                    args={
                        "x": belief.position.x,
                        "y": belief.position.y,
                        "z": belief.position.z,
                        "tolerance_m": 1.5,
                        "label": self.target_label,
                    },
                ),
                belief.confidence,
                note=belief.source,
            )

        self._lost_ticks += 1
        # A bounded vocabulary means the response to "lost" is a skill, not an
        # improvised trajectory: scan for evidence, then commit to a search leg.
        if self.scan_when_lost and self._lost_ticks % 3 == 1:
            return self.envelope(
                ctx,
                DecisionKind.SKILL,
                SkillCall(skill_name="scan", args={"yaw_rate_rps": 0.8, "duration_s": 1.0}),
                0.1,
                note="searching",
            )
        target = self.explore_target(ctx)
        return self.envelope(
            ctx,
            DecisionKind.SKILL,
            SkillCall(
                skill_name="goto",
                args={"x": target.x, "y": target.y, "z": target.z, "tolerance_m": 2.5},
            ),
            0.1,
            note="exploration",
        )


# --------------------------------------------------------------------------
# Learned-action authority
# --------------------------------------------------------------------------


class _VLABase(BasePolicy):
    """Shared servoing behaviour for the learned-action family.

    There is no learning here and no vision here. This is closed-form geometry:
    a unit vector from the current position to a believed target position,
    scaled by a cruise speed, plus a repulsive term from the depth fan. It
    occupies the *slot* a VLA occupies — same authority level, same action
    representation, same inference cost charged to the clock — so that the
    runtime and the contracts can be exercised before a checkpoint exists.

    What it therefore cannot tell you: anything about visuomotor competence,
    visual generalisation, or language grounding. Those are the questions C7-C14
    are meant to answer, and answering them requires a real model in this slot.
    """

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "sim-vla")
        super().__init__(**params)
        self.cruise_mps = float(params.get("cruise_mps", 3.0))
        self.action_duration_s = float(params.get("action_duration_s", 0.2))
        self.avoid_gain = float(params.get("avoid_gain", 1.2))
        """How strongly the learned policy itself reacts to close geometry.

        Non-zero because a competent VLA does avoid obstacles; well below what a
        planner achieves, because that difference is what C7 is meant to expose.
        """

    def _action_velocity(self, ctx: DecisionContext, belief: TargetBelief) -> Vec3:
        position = ctx.observation.position
        if belief.known and belief.position is not None:
            ux, uy, uz = _unit_toward(position, belief.position)
        else:
            heading = self.explore_heading(ctx)
            ux, uy, uz = math.cos(heading), math.sin(heading), 0.0

        vx, vy, vz = ux * self.cruise_mps, uy * self.cruise_mps, uz * self.cruise_mps
        obs = ctx.observation
        if obs.range_rays and self.avoid_gain > 0.0:
            # NOT learned. A hand-written repulsive potential field, standing in
            # for the reactive avoidance a real VLA would have absorbed from
            # training data. Calling it "learned" in an earlier version of this
            # comment was exactly the kind of label that makes a scripted
            # baseline read as a model result.
            idx = min(range(len(obs.range_rays)), key=lambda i: obs.range_rays[i])
            nearest = obs.range_rays[idx]
            if nearest < 4.0:
                bearing = obs.ray_bearings_rad[idx] + obs.yaw_rad
                strength = self.avoid_gain * (4.0 - nearest) / 4.0
                vx -= strength * math.cos(bearing) * self.cruise_mps
                vy -= strength * math.sin(bearing) * self.cruise_mps
        return Vec3(x=vx, y=vy, z=vz)


@register("policy", "mock_vla")
class MockVLAPolicy(_VLABase):
    """One learned kinematic action per inference (CognitiveDrone/AeroVLA shape)."""

    @property
    def name(self) -> str:
        return "mock_vla"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("kinematic_action", "mission_directive")

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        await self.charge(ctx)
        belief = self.believe(ctx)
        if self.should_stop(belief, ctx):
            self._stopped = True
            return self.envelope(
                ctx,
                DecisionKind.MISSION_DIRECTIVE,
                MissionDirective(label=ProgressLabel.STOP, rationale="VLA stop action"),
                belief.confidence,
            )
        return self.envelope(
            ctx,
            DecisionKind.KINEMATIC_ACTION,
            KinematicAction(
                velocity=self._action_velocity(ctx, belief),
                yaw_rate_rps=self._yaw_rate(ctx, belief),
                duration_s=self.action_duration_s,
            ),
            belief.confidence,
            note=belief.source,
        )

    def _yaw_rate(self, ctx: DecisionContext, belief: TargetBelief) -> float:
        if not belief.known or belief.position is None:
            return 0.4
        position = ctx.observation.position
        desired = math.atan2(belief.position.y - position.y, belief.position.x - position.x)
        delta = math.atan2(
            math.sin(desired - ctx.observation.yaw_rad), math.cos(desired - ctx.observation.yaw_rad)
        )
        return max(-1.5, min(1.5, delta * 1.2))


@register("policy", "chunk_vla")
class ChunkVLAPolicy(_VLABase):
    """A short receding-horizon action chunk per inference (FLIGHT/ScoutVLA shape).

    The chunk is what lets a fast executor keep flying smoothly under a slow
    semantic loop — and also what makes stale intent persist longer, which is
    the trade-off C11 and C12 are built to measure.
    """

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.chunk_length = int(params.get("chunk_length", 4))
        self.replan_after = params.get("replan_after")
        self.curvature_decay = float(params.get("curvature_decay", 0.85))

    @property
    def name(self) -> str:
        return "chunk_vla"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("action_chunk", "mission_directive")

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        await self.charge(ctx)
        belief = self.believe(ctx)
        if self.should_stop(belief, ctx):
            self._stopped = True
            return self.envelope(
                ctx,
                DecisionKind.MISSION_DIRECTIVE,
                MissionDirective(label=ProgressLabel.STOP, rationale="VLA stop action"),
                belief.confidence,
            )

        base = self._action_velocity(ctx, belief)
        actions = []
        scale = 1.0
        for _ in range(max(2, self.chunk_length)):
            actions.append(
                KinematicAction(
                    velocity=Vec3(x=base.x * scale, y=base.y * scale, z=base.z * scale),
                    yaw_rate_rps=0.0,
                    duration_s=self.action_duration_s,
                )
            )
            # Later steps in the chunk are predictions, not observations, so the
            # policy commits to them less strongly.
            scale *= self.curvature_decay
        return self.envelope(
            ctx,
            DecisionKind.ACTION_CHUNK,
            ActionChunk(
                actions=tuple(actions),
                replan_after=int(self.replan_after) if self.replan_after else None,
            ),
            belief.confidence,
            note=belief.source,
        )


@register("policy", "world_model_vla")
class WorldModelVLAPolicy(ChunkVLAPolicy):
    """Chunked VLA with an explicit predicted future state (WorldFly shape).

    When the target is currently unobservable, the predicted state carries the
    belief forward by dead reckoning instead of dropping it.  The sentinel
    question for C14 is whether that extra machinery earns its keep specifically
    under occlusion and sharp viewpoint change — and nowhere else.
    """

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.prediction_horizon_s = float(params.get("prediction_horizon_s", 1.0))
        self._predicted: Vec3 | None = None
        self._predicted_at_ns: int = 0

    @property
    def name(self) -> str:
        return "world_model_vla"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self._predicted = None
        self._predicted_at_ns = 0

    def believe(self, ctx: DecisionContext) -> TargetBelief:
        belief = super().believe(ctx)
        if belief.known:
            self._predicted = belief.position
            self._predicted_at_ns = ctx.t_sim_ns
            return belief
        if self._predicted is not None:
            age_s = (ctx.t_sim_ns - self._predicted_at_ns) / 1e9
            if age_s <= self.prediction_horizon_s * 4.0:
                # Confidence decays with the age of the prediction, so a stale
                # world model cannot masquerade as a live observation.
                decay = max(0.0, 1.0 - age_s / (self.prediction_horizon_s * 4.0))
                return TargetBelief(self._predicted, 0.6 * decay, "world_model")
        return belief
