"""VLM-authored adaptive plan with SPF waypoint execution (D-101).

Component-level clean-room adaptation of MapGPT Sec. 3.3 and SPF's geometric
interface, with expected-view assessment inspired by FineCog-Nav. This is not
full MapGPT: no simulator-provided graph or navigation candidates are supplied.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from copy import deepcopy
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from uavlab.contracts import DecisionKind, MissionSpec, Vec3, WaypointGoal
from uavlab.contracts.events import EventType
from uavlab.core.frame_store import global_store
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext, InferenceRequest
from uavlab.plugins.reasoning.base import BasePolicy
from uavlab.plugins.reasoning.onfly import _encode_png
from uavlab.plugins.reasoning.spf import SPFPoint, adaptive_distance_m, point_to_enu


class PlanValue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Subgoal(PlanValue):
    id: str = Field(min_length=1, max_length=24, pattern=r"^[a-zA-Z0-9_-]+$")
    objective: str = Field(min_length=1, max_length=140)
    expected_view: str = Field(min_length=1, max_length=140)


class Move(PlanValue):
    mode: Literal["move"]
    u: int = Field(ge=0, le=1000)
    v: int = Field(ge=0, le=1000)
    distance: int = Field(ge=1, le=10)


class Retain(PlanValue):
    mode: Literal["retain"]


class PlanReply(PlanValue):
    assessment: Literal["ongoing", "achieved", "blocked", "uncertain"]
    reason: str = Field(min_length=1, max_length=200)
    plan: list[Subgoal] = Field(min_length=1, max_length=5)
    active_id: str = Field(min_length=1, max_length=24)
    scene_memory: str = Field(max_length=360)
    action: Annotated[Move | Retain, Field(discriminator="mode")]

    @model_validator(mode="after")
    def check_identity(self):
        ids = [step.id for step in self.plan]
        if len(ids) != len(set(ids)) or self.active_id not in ids:
            raise ValueError("plan IDs must be unique and active_id must name a listed subgoal")
        return self

    def active(self) -> Subgoal:
        return next(step for step in self.plan if step.id == self.active_id)


PROMPT = """You are the navigation planner of a drone. You author the intermediate
objectives, their order, and the next motion destination. Use the current forward
RGB image, mission, previous plan, your scene memory, and measured execution history.

Return strict JSON matching the schema. Write 1-5 ordered subgoals in plan, with
stable IDs, an objective and the expected visual change at completion. Keep IDs
for unchanged subgoals. Set active_id to the subgoal you choose to execute now.
Assess the PREVIOUS active subgoal as ongoing, achieved, blocked, or uncertain;
explain briefly what observed evidence supports continuing or changing the plan.
The next plan may keep, reorder, add or remove steps. Update scene_memory with
useful observations and failed attempts; distinguish observations from hypotheses.
Expected views are predictions, not proof that a step succeeded.

Seeing the target does not establish a traversable route. Consider obstacle faces,
openings, clearance uncertainty and which intermediate view could reveal a route.
Propose your own subgoals and point; no route or candidate list is provided.
The classical executor only checks feasibility and routes toward YOUR destination.
A routing acceptance is not arrival or semantic completion. Distance to a waypoint
is measured to YOUR proposed point, never to the true mission target.

For a new destination return action={"mode":"move","u":...,"v":...,"distance":...}.
Coordinates use a 1000x1000 reference: top-left (0,0), center (500,500), bottom-right
(1000,1000). distance is intended CAMERA-FORWARD travel, not obstacle depth:
{distance_scale}
Choose the point and travel for the ACTIVE intermediate objective, not necessarily
the final target. A small move does not mean mission complete.

To continue toward the unchanged active subgoal and previously proposed WORLD
point, return action={"mode":"retain"}. This preserves that point despite camera
motion. It requires an existing point and the same active subgoal ID and content.
To change the subgoal or destination use move. Arrival does not automatically
advance the plan: decide from the image and feedback. An independent monitor owns
final mission stopping. Do not issue flight controls or claim hidden geometry.
Keep text fields concise and distinguish visible facts from your inference.
"""


@register("policy", "adaptive_visual_plan")
class AdaptiveVisualPlanPolicy(BasePolicy):
    requires_vision = True
    requires_real_inference = True

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "gemma4:e2b")
        params.setdefault("self_terminate", False)
        super().__init__(**params)
        self.scale_m = float(params.get("scale_m", 7.0))
        self.exponent = float(params.get("exponent", 1.8))
        self.camera_pitch_rad = float(params.get("camera_pitch_rad", -0.15))
        self.tolerance_m = float(params.get("waypoint_tolerance_m", 0.35))
        self.history_limit = int(params.get("history_limit", 12))
        if not all(
            math.isfinite(x) and x > 0 for x in (self.scale_m, self.exponent, self.tolerance_m)
        ):
            raise ValueError("travel scale, exponent and tolerance must be finite and positive")
        if not math.isfinite(self.camera_pitch_rad) or not 1 <= self.history_limit <= 32:
            raise ValueError("finite camera pitch and history_limit in 1..32 required")
        self._clear()

    @property
    def name(self) -> str:
        return "adaptive_visual_plan"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("waypoint",)

    def _clear(self) -> None:
        self._reply: PlanReply | None = None
        self._target: Vec3 | None = None
        self._origin: dict[str, Any] | None = None
        self._history: deque[dict[str, Any]] = deque(maxlen=self.history_limit)
        self._revision = 0
        self.model_calls = 0
        self.invalid_outputs = 0
        self.retained_goals = 0

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self._clear()

    def snapshot(self) -> dict[str, Any]:
        """Serializable model belief and measured history for inspection, not truth."""
        return deepcopy(
            {
                "revision": self._revision,
                "previous_response": self._reply.model_dump(mode="json") if self._reply else None,
                "proposed_world_point": self._target.model_dump() if self._target else None,
                "point_origin": self._origin,
                "history": list(self._history),
            }
        )

    def _input_state(self, ctx: DecisionContext) -> dict[str, Any]:
        # Match feedback to an issued ID, not simply the most recent model call:
        # a slow result may arrive after another observation or proposal.
        feedback = ctx.last_routing_feedback
        if feedback is not None:
            for entry in self._history:
                if entry["decision_id"] == feedback.decision_id:
                    entry["routing"] = {
                        "accepted_not_completed": feedback.accepted,
                        "reason": feedback.reason[:500],
                        "t_sim_ns": feedback.t_sim_ns,
                    }
                    break
        obs = ctx.observation
        state = self.snapshot()
        state.update(
            {
                "instruction": ctx.mission.instruction,
                "observation_seq": obs.seq,
                "t_sim_ns": obs.t_sim_ns,
                "position_enu_m": obs.position.model_dump(),
                "yaw_rad": obs.yaw_rad,
                "mission_constraints": ctx.mission.constraints.model_dump(mode="json"),
                "distance_to_proposed_point_m": (
                    obs.position.distance_to(self._target) if self._target else None
                ),
            }
        )
        return state

    async def decide(self, ctx: DecisionContext):
        if self.services is None or self.services.inference is None:
            raise RuntimeError("adaptive visual planning requires an inference backend")
        obs = ctx.observation
        if obs.rgb is None or obs.intrinsics is None:
            raise RuntimeError("adaptive visual planning requires RGB and camera intrinsics")
        image = global_store().get(obs.rgb.uri)
        if image is None:
            raise RuntimeError("adaptive visual planning RGB frame is missing")
        state = self._input_state(ctx)
        distances = ", ".join(
            f"{i}={adaptive_distance_m(i, scale_m=self.scale_m, exponent=self.exponent):.2f}m"
            for i in range(1, 11)
        )
        prompt = PROMPT.replace("{distance_scale}", distances)
        prompt += "\nINPUT STATE:\n" + json.dumps(state, ensure_ascii=False)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        result = await self.services.inference.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role="policy",
                prompt_hash=prompt_hash,
                input_tokens=max(1, len(prompt) // 4),
                image_count=1,
                observation_seq=obs.seq,
                prompt=prompt,
                images=(_encode_png(image),),
                response_schema=PlanReply.model_json_schema(),
            )
        )
        self.model_calls += 1
        try:
            if not isinstance(result.payload, str):
                raise ValueError("response must be JSON text")
            reply = PlanReply.model_validate_json(result.payload)
            target, origin = self._resolve(reply, ctx)
        except (ValueError, ValidationError) as exc:
            self.invalid_outputs += 1
            raise RuntimeError(f"invalid adaptive visual plan: {exc}") from exc

        # Commit only after the entire plan/action contract passes. No classical
        # substitution, auto-advancement, or retained-pixel re-projection occurs.
        changed = self._reply is None or (
            reply.plan != self._reply.plan or reply.active_id != self._reply.active_id
        )
        revision = self._revision + int(changed)
        envelope = self.envelope(
            ctx,
            DecisionKind.WAYPOINT,
            WaypointGoal(target=target, target_label=None, tolerance_m=origin["tolerance_m"]),
            0.65,
            note="model-authored adaptive plan with SPF waypoint",
            extra={
                "plan_revision": str(revision),
                "active_subgoal_id": reply.active_id,
                "action_mode": reply.action.mode,
                "prompt_hash": prompt_hash,
                "rgb_digest": obs.rgb.digest,
                "point_source_observation_seq": str(origin["observation_seq"]),
                "implementation": "mapgpt_component_spf_adaptation",
                **(
                    {
                        "pixel_u": str(reply.action.u * obs.intrinsics.width / 1000),
                        "pixel_v": str(reply.action.v * obs.intrinsics.height / 1000),
                    }
                    if isinstance(reply.action, Move)
                    else {}
                ),
            },
        )
        self._reply, self._target, self._origin = reply, target, origin
        self._revision = revision
        self.retained_goals += int(isinstance(reply.action, Retain))
        self._history.append(
            {
                "decision_id": envelope.decision_id,
                "t_sim_ns": obs.t_sim_ns,
                "position_enu_m": obs.position.model_dump(),
                "yaw_rad": obs.yaw_rad,
                "active_id": reply.active_id,
                "action_mode": reply.action.mode,
                "proposed_world_point": target.model_dump(),
                "routing": None,
            }
        )
        self.services.log.emit(
            self.name,
            EventType.MEMORY_UPDATE,
            envelope.produced_t_sim_ns,
            envelope.produced_t_wall_ns,
            payload={
                "kind": "adaptive_visual_plan",
                "input_state": state,
                "response": reply.model_dump(mode="json"),
                "revision": revision,
                "proposed_world_point": target.model_dump(),
                "point_origin": origin,
            },
            trace_id=envelope.decision_id,
        )
        return envelope

    def _resolve(self, reply: PlanReply, ctx: DecisionContext) -> tuple[Vec3, dict]:
        if isinstance(reply.action, Retain):
            if self._target is None or self._origin is None or self._reply is None:
                raise ValueError("retain requires an existing world point")
            if reply.active() != self._reply.active():
                raise ValueError("retain requires the same active subgoal; use move for a new one")
            return self._target, self._origin
        obs, action = ctx.observation, reply.action
        intr = obs.intrinsics
        assert intr is not None
        distance = adaptive_distance_m(
            action.distance,
            scale_m=self.scale_m,
            exponent=self.exponent,
        )
        target = point_to_enu(
            SPFPoint(action.u, action.v, action.distance),
            position=obs.position,
            yaw_rad=obs.yaw_rad,
            width=intr.width,
            height=intr.height,
            fx=intr.fx,
            fy=intr.fy,
            cx=intr.cx,
            cy=intr.cy,
            camera_pitch_rad=self.camera_pitch_rad,
            distance_m=distance,
            min_altitude_m=self._min_alt,
        )
        return target, {
            "observation_seq": obs.seq,
            "position_enu_m": obs.position.model_dump(),
            "yaw_rad": obs.yaw_rad,
            "u": action.u,
            "v": action.v,
            "distance_label": action.distance,
            "camera_forward_m": distance,
            "tolerance_m": min(self.tolerance_m, max(distance * 0.5, 0.05)),
        }

    def stats(self) -> dict[str, float]:
        return {
            "adaptive_plan_calls": float(self.model_calls),
            "adaptive_plan_invalid_outputs": float(self.invalid_outputs),
            "adaptive_plan_revisions": float(self._revision),
            "adaptive_plan_retained_goals": float(self.retained_goals),
        }
