"""Model-requested visual perception for the skill-level AerialClaw agent.

The planner receives text and chooses skills. Only detect_object consumes RGB;
its object location is evidence, never a navigation command. SUPER is unchanged.
"""

from __future__ import annotations

import base64
import io
import json
import math
from dataclasses import replace

import numpy as np
from pydantic import Field, StrictBool, StrictInt

from uavlab.contracts import MemoryItem, SkillCall, StrictModel, Vec3, s_to_ns
from uavlab.contracts.events import EventType
from uavlab.core.frame_store import global_store
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext, InferenceRequest
from uavlab.plugins.reasoning.aerialclaw import AerialClawAgentPolicy


class ObjectLocation(StrictModel):
    visible: StrictBool
    u: StrictInt | None = Field(ge=0, le=999)
    v: StrictInt | None = Field(ge=0, le=999)


def locate_in_depth(
    answer: ObjectLocation,
    ctx: DecisionContext,
    depth,
    pitch: float,
    refinement_fraction: float = 0.0,
):
    """Lift the selected object pixel using synchronized depth and actual intrinsics."""
    if not answer.visible:
        if answer.u is not None or answer.v is not None:
            raise ValueError("absent object must have null coordinates")
        return None, None
    if answer.u is None or answer.v is None:
        raise ValueError("visible object requires both coordinates")
    intr = ctx.observation.intrinsics
    if intr is None or depth.shape != (intr.height, intr.width):
        raise ValueError("depth and intrinsics must match")
    u, v = answer.u * (intr.width - 1) / 999, answer.v * (intr.height - 1) / 999
    x, y = round(u), round(v)
    distance = float(depth[y, x])
    if not math.isfinite(distance) or distance <= 0:
        # Opt-in bounded pixel localization tolerance. Require one connected,
        # consistent observed surface; never assign depth to the original empty ray.
        radius = math.ceil(min(intr.width, intr.height) * refinement_fraction)
        if radius <= 0:
            return None, None
        y0, x0 = max(0, y - radius), max(0, x - radius)
        patch = depth[y0 : y + radius + 1, x0 : x + radius + 1]
        mask = np.isfinite(patch) & (patch > 0)
        ys, xs = np.where(mask)
        if len(xs) < 3:
            return None, None
        values = patch[mask]
        if float(np.ptp(values)) > max(0.25, 0.05 * float(np.median(values))):
            return None, None
        cells = set(zip(ys.tolist(), xs.tolist(), strict=True))
        pending = [cells.pop()]
        while pending:
            row, col = pending.pop()
            for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                other = row + dr, col + dc
                if other in cells:
                    cells.remove(other)
                    pending.append(other)
        if cells:  # Several disconnected surfaces are ambiguous.
            return None, None
        nearest = int(np.argmin((xs + x0 - u) ** 2 + (ys + y0 - v) ** 2))
        x, y = int(xs[nearest] + x0), int(ys[nearest] + y0)
        u, v = float(x), float(y)
        distance = float(depth[y, x])
    left = (intr.cx - u) * distance / intr.fx
    up_camera = (intr.cy - v) * distance / intr.fy
    cp, sp = math.cos(-pitch), math.sin(-pitch)
    forward, up = distance * cp + up_camera * sp, -distance * sp + up_camera * cp
    yaw = ctx.observation.yaw_rad
    p = ctx.observation.position
    return Vec3(
        x=p.x + forward * math.cos(yaw) - left * math.sin(yaw),
        y=p.y + forward * math.sin(yaw) + left * math.cos(yaw),
        z=p.z + up,
    ), distance


@register("policy", "aerialclaw_visual_agent")
class AerialClawVisualAgentPolicy(AerialClawAgentPolicy):
    """Opt-in single-object perception tool; never silently replaces the text profile."""

    def __init__(self, **params):
        super().__init__(**params)
        self.query = str(params.get("visual_target_query", "")).strip()
        self.visual_search_strategy = bool(params.get("visual_search_strategy", False))
        self.pitch = float(params.get("camera_pitch_rad", -0.10))
        self.refinement_fraction = float(params.get("pixel_refinement_fraction", 0.0))
        if not 0.0 <= self.refinement_fraction <= 0.03:
            raise ValueError("pixel refinement must be within 0..3% of image size")
        self._pending = None
        self._visual_memory = None
        self._last_inspection = None
        self._tool_calls = 0

    @property
    def name(self):
        return "aerialclaw_visual_agent"

    def reset(self, mission, seed):
        super().reset(mission, seed)
        if not self.query or "detect_object" not in self.skill_allowlist:
            raise ValueError("visual profile requires a public object query and detect_object")
        if self.query.casefold() not in mission.instruction.casefold():
            raise ValueError("visual_target_query must occur in the public mission instruction")
        if "detect_object" not in mission.allowed_skills:
            raise ValueError("mission must allow detect_object")
        self._pending = self._visual_memory = self._last_inspection = None
        self._tool_calls = 0

    def stats(self):
        return {**super().stats(), "aerialclaw_visual_tool_calls": float(self._tool_calls)}

    def _context_with_visual_memory(self, ctx):
        item = self._visual_memory
        if item is None or not 0 <= ctx.t_sim_ns - item.t_sim_ns <= s_to_ns(10.0):
            return ctx
        memory = ctx.memory.model_copy(update={"items": (*ctx.memory.items, item)})
        return replace(ctx, memory=memory)

    def _soft_skill_phase(self, ctx, completion):
        phase = super()._soft_skill_phase(ctx, completion)
        if phase in ("complete_supported_arrival", "approach_exact_label_target"):
            return phase
        if self._last_inspection is None:
            return "inspect_current_viewpoint"
        position, yaw = self._last_inspection
        delta = abs((ctx.observation.yaw_rad - yaw + math.pi) % (2 * math.pi) - math.pi)
        if position.distance_to(ctx.observation.position) > 0.5 or delta > 0.3:
            return "inspect_current_viewpoint"
        return phase

    def _build_prompt(self, ctx):
        text = super()._build_prompt(ctx)
        if self.visual_search_strategy:
            start = text.index("## Relevant soft skill")
            end = text.index("## BODY-derived coverage reference", start)
            text = (
                text[:start]
                + """## Relevant soft skill: search with requested perception
Passive detections are unavailable. Empty detections do NOT establish absence.
A scan rotates the camera but never identifies objects.
When phase is inspect_current_viewpoint, first call detect_object to inspect the view.
After a negative detection, scan to change heading, then request detect_object again.
Use coverage goto after inspecting searched viewpoints without finding the target.
After a positive result, choose goto to the measured target, await skill feedback,
and choose done when completion evidence supports arrival.
Do not generate a stream of image navigation points.

"""
                + text[end:]
            )
        return (
            text
            + f"""

## Additional perception hard skill (no flight command)
- detect_object: args must be {{"query": {json.dumps(self.query)}}}.
This queries the current camera once and returns an estimated object position or not-found.
The normalized semantic label 'target' means exactly {self.query!r} in this mission.
You do not receive images. Use detect_object to obtain visual evidence; do not infer
absence from the empty passive detector. inspect_current_viewpoint permits detect_object.
After a successful detection, choose goto using the returned world position, then done
when completion evidence supports it. A goto continues through SUPER without new model
navigation points. If not found, choose scan or another search skill and inspect again.
"""
        )

    def _emit_tool(self, ctx, payload, trace):
        services, _ = self._runtime()
        services.log.emit(
            self.name,
            EventType.SKILL_TOOL,
            services.clock.now_ns(),
            services.clock.wall_ns(),
            payload,
            trace_id=trace,
        )

    async def decide(self, ctx):
        # Capture on the NEXT observation after the model requests the tool, not
        # the potentially old observation from before the text-planning call.
        if self._pending is not None:
            trace = self._pending
            self._pending = None
            await self._inspect(ctx, trace)
            return None
        envelope = await super().decide(self._context_with_visual_memory(ctx))
        if envelope is None or not isinstance(envelope.payload, SkillCall):
            return envelope
        if envelope.payload.skill_name != "detect_object":
            return envelope
        valid = envelope.payload.args == {"query": self.query}
        self._history[-1]["feedback"] = {
            "dispatch_accepted": valid,
            "dispatch_reason_not_completion": "perception tool queued"
            if valid
            else "detect_object requires the declared query only",
            "skill_completed": False,
        }
        self._emit_tool(
            ctx,
            {
                "phase": "requested",
                "role": "policy",
                "source_observation_seq": ctx.observation.seq,
                "skill": "detect_object",
                "args": envelope.payload.args,
                "accepted": valid,
                "producer": self.name,
            },
            envelope.decision_id,
        )
        if valid:
            self._pending = envelope.decision_id
        return None  # Perception never dispatches a waypoint or control command.

    async def _inspect(self, ctx, trace):
        services, backend = self._runtime()
        obs = ctx.observation
        if obs.rgb is None or obs.depth is None or obs.intrinsics is None:
            raise ValueError("detect_object requires synchronized RGB, depth and intrinsics")
        rgb = global_store().get(obs.rgb.uri)
        depth = np.asarray(global_store().get(obs.depth.uri)).copy()
        buffer = io.BytesIO()
        rgb.convert("RGB").save(buffer, format="PNG")
        prompt = (
            f"Locate the {self.query} in this image. This is object detection, not navigation. "
            "Match the requested object and color exactly. Return its visual center as integer u,v "
            "on a 0..999 grid, top-left origin. If absent return visible=false and null u,v. "
            "Return only JSON with visible,u,v. Do not select an open path or invent an object."
        )
        result = await backend.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role="perception",
                prompt_hash="aerialclaw:detect_object:v1",
                input_tokens=len(prompt) // 4,
                image_count=1,
                images=(base64.b64encode(buffer.getvalue()).decode("ascii"),),
                observation_seq=obs.seq,
                prompt=prompt,
                response_schema=ObjectLocation.model_json_schema(),
            )
        )
        self._tool_calls += 1
        self._visual_memory = None
        answer = ObjectLocation.model_validate_json(str(result.payload))
        position, depth_m = locate_in_depth(
            answer, ctx, depth, self.pitch, self.refinement_fraction
        )
        self._last_inspection = (obs.position, obs.yaw_rad)
        if position is not None:
            self._visual_memory = MemoryItem(
                observation_seq=obs.seq,
                t_sim_ns=obs.t_sim_ns,
                kind="visual_tool",
                label=self.target_label,
                position=position,
                salience=1.0,
                summary=f"detect_object observed {self.query}; RGB-D position estimate",
                image_uri=obs.rgb.uri,
            )
        feedback = {
            "dispatch_accepted": True,
            "skill_completed": True,
            "dispatch_reason_not_completion": "object localized"
            if position
            else "no ranged detection",
            "query": self.query,
            "visible": answer.visible,
            "position_enu_m": position.model_dump() if position else None,
            "source_observation_seq": obs.seq,
            "source_t_sim_ns": obs.t_sim_ns,
            "sampled_depth_m": depth_m,
            "pixel_refinement_fraction": self.refinement_fraction,
        }
        self._history[-1]["feedback"] = feedback
        self._emit_tool(
            ctx,
            {
                **feedback,
                "phase": "completed",
                "role": "perception",
                "pixel_u": answer.u,
                "pixel_v": answer.v,
            },
            trace + "-result",
        )
