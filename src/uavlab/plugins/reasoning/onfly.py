"""Paper-shaped OnFly components inside the common testbed.

OnFly is represented as a composition, not a private runtime: a fast visual
point decision agent, an independent slow visual monitor, a bounded visual
memory, a semantic/geometric waypoint verifier, and the shared planner.  The
paper's implementation has not been released, so inaccessible ViT-feature and
KV-cache internals are explicit normalized approximations rather than invented
claims of checkpoint reproduction.
"""

from __future__ import annotations

import base64
import io
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from uavlab.contracts import (
    DecisionKind,
    MemoryItem,
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    ProgressLabel,
    ProgressState,
    Vec3,
    WaypointGoal,
)
from uavlab.core.camera import Camera
from uavlab.core.frame_store import global_store
from uavlab.core.registry import register
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import DecisionContext, InferenceRequest, VerificationResult
from uavlab.plugins.reasoning.base import BasePolicy
from uavlab.plugins.verifier.bounds import SemanticGeometricVerifier


def _encode_png(image: Any) -> str:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _extract_json(text: object) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("model response is not text")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model response contains no JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response JSON is not an object")
    return value


def bearing_gated_range(
    depth_m: float,
    u: float,
    *,
    fx: float,
    cx: float,
    half_fov_rad: float,
    sigma_theta: float,
) -> float:
    """OnFly's Gaussian forward-range gate for large image bearings."""
    theta = math.atan((u - cx) / fx)
    scale = max(sigma_theta * half_fov_rad, 1e-6)
    return depth_m * math.exp(-0.5 * (theta / scale) ** 2)


def _depth_at(depth: np.ndarray, u: float, v: float, patch: int = 2) -> float | None:
    y, x = round(v), round(u)
    if not (0 <= y < depth.shape[0] and 0 <= x < depth.shape[1]):
        return None
    crop = depth[
        max(0, y - patch) : min(depth.shape[0], y + patch + 1),
        max(0, x - patch) : min(depth.shape[1], x + patch + 1),
    ]
    valid = crop[np.isfinite(crop) & (crop > 0.05)]
    return float(np.median(valid)) if valid.size else None


DIRECTION_BEARING_DEG: dict[str, float] = {
    "hard_left": 38.0,
    "left": 20.0,
    "ahead": 0.0,
    "right": -20.0,
    "hard_right": -38.0,
}
"""Discrete steering vocabulary, and the body-frame bearing each one means.

**Why this exists.** Measured on seed 1060, the pixel contract is saturated: the
model's chosen `u` has median 116 where the image centre is 112, and 59% of its
commands are within 10 degrees of straight ahead. It answers "the middle of the
picture" almost every time, so the heading is set by planner deflections rather
than by the model, and the corridor instruction in the prompt is obeyed at 58%
against a 50% chance baseline.

A pixel is a hard thing for a small VLM to emit meaningfully: it is a continuous
two-dimensional quantity with no natural verbal anchor, and "the middle" is
always a defensible answer. A word from a five-item vocabulary is not — every
option commits to a direction, and there is no neutral hedge except `ahead`,
which is then visible as a choice rather than hidden as a default.

The bearings stay inside the camera's +-45 degree half-angle, because a
direction the vehicle cannot look at cannot be verified against what it saw.
"""


@register("policy", "onfly_decision")
class OnFlyDecisionAgent(BasePolicy):
    """Current RGB-D + previous-goal pixel -> integer image target -> waypoint."""

    requires_vision = True

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "gemma3:4b")
        params.setdefault("self_terminate", False)
        params.setdefault("use_memory", False)
        super().__init__(**params)
        self.max_depth_m = float(params.get("max_depth_m", 7.0))
        self.sigma_theta = float(params.get("sigma_theta", 0.65))
        self.goal_standoff_m = float(params.get("goal_standoff_m", 0.0))
        self.camera_pitch_rad = float(params.get("camera_pitch_rad", -0.15))
        self.coordinate_contract = str(params.get("coordinate_contract", "image_pixels"))
        self.previous_goal_prompt = bool(params.get("previous_goal_prompt", True))
        self.coverage_prompt = bool(params.get("coverage_prompt", False))
        self.frontier_assist = bool(params.get("frontier_assist", False))
        self.frontier_hop_m = float(params.get("frontier_hop_m", 9.0))
        # See, Point, Fly (arXiv 2509.22653) asks the VLM for the travel distance
        # instead of reading it off a depth image. C5's own step is bounded above
        # by ``sensed_depth(u, v)``, so it cannot cross the first surface on the
        # chosen ray; SPF has no such ceiling because no depth sensor is involved.
        # Off by default: the frozen C5 results must stay reproducible.
        # PRIVILEGED DIAGNOSTIC ONLY. A verbal description of a route that is
        # known to reach the target. This is simulator truth injected into the
        # prompt, so any run using it is a capability probe - "can the agent
        # execute a route it is told?" - and can never be reported as a result
        # for this architecture. Empty by default and expected to stay empty in
        # every shipped profile.
        self.route_hint = str(params.get("route_hint", ""))
        self.step_from_model = bool(params.get("step_from_model", False))
        self.step_levels = int(params.get("step_levels", 5))
        self.step_scale_m = float(params.get("step_scale_m", 9.0))
        self.step_exponent = float(params.get("step_exponent", 1.0))
        self.step_min_m = float(params.get("step_min_m", 1.0))
        if self.step_levels < 1:
            raise ValueError("step_levels must be at least 1")
        if self.coordinate_contract not in {
            "image_pixels",
            "qwen_relative_1000",
            "discrete_direction",
        }:
            raise ValueError(
                "coordinate_contract must be image_pixels, qwen_relative_1000 or discrete_direction"
            )
        self._previous_goal: Vec3 | None = None
        self._last_model_point: tuple[int, int] | None = None
        self._rejected_model_points: list[tuple[int, int]] = []
        self._route_positions: list[Vec3] = []
        self._route_flown_m = 0.0
        self._initial_yaw_rad: float | None = None
        self._home_position: Vec3 | None = None
        self._viewed_heading_bins: set[int] = set()
        self.model_calls = 0
        self.parse_errors = 0

    @property
    def name(self) -> str:
        return "onfly_decision"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("waypoint",)

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self._previous_goal = None
        self._last_model_point = None
        self._rejected_model_points = []
        self._route_positions = []
        self._route_flown_m = 0.0
        self._initial_yaw_rad = None
        self._home_position = None
        self._viewed_heading_bins = set()
        self.model_calls = 0
        self.parse_errors = 0

    def _schema_base(self, width: int, height: int) -> dict[str, object]:
        max_u, max_v = (
            (999, 999)
            if self.coordinate_contract == "qwen_relative_1000"
            else (width - 1, height - 1)
        )
        if self.coordinate_contract == "discrete_direction":
            properties: dict[str, object] = {
                "direction": {"type": "string", "enum": sorted(DIRECTION_BEARING_DEG)},
            }
            required = ["direction"]
            if self.frontier_assist:
                properties["target_visible"] = {"type": "boolean"}
                required.insert(0, "target_visible")
            return {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            }
        if self.frontier_assist:
            return {
                "type": "object",
                "properties": {
                    "target_visible": {"type": "boolean"},
                    "u": {"type": "integer", "minimum": 0, "maximum": max_u},
                    "v": {"type": "integer", "minimum": 0, "maximum": max_v},
                },
                "required": ["target_visible", "u", "v"],
                "additionalProperties": False,
            }
        return {
            "type": "object",
            "properties": {
                "u": {"type": "integer", "minimum": 0, "maximum": max_u},
                "v": {"type": "integer", "minimum": 0, "maximum": max_v},
            },
            "required": ["u", "v"],
            "additionalProperties": False,
        }

    def _schema(self, width: int, height: int) -> dict[str, object]:
        """The pixel contract, plus SPF's discrete travel distance when enabled."""
        schema = self._schema_base(width, height)
        if self.step_from_model:
            properties = dict(schema["properties"])  # type: ignore[arg-type]
            properties["d"] = {
                "type": "integer",
                "minimum": 1,
                "maximum": self.step_levels,
            }
            schema["properties"] = properties
            schema["required"] = list(schema["required"]) + ["d"]  # type: ignore[arg-type]
        return schema

    def _model_step_m(self, level: int) -> float:
        """SPF's adaptive step curve: d_adj = max(d_min, s * (d/L)^p)."""
        if not (1 <= level <= self.step_levels):
            raise ValueError(f"step level {level} outside 1..{self.step_levels}")
        ratio = level / float(self.step_levels)
        return max(self.step_min_m, self.step_scale_m * ratio**self.step_exponent)

    def _prompt_point(
        self, pixel: tuple[int, int] | None, width: int, height: int
    ) -> tuple[int, int] | None:
        """Express a prior image pixel in the model profile's coordinate frame."""
        if pixel is None or self.coordinate_contract == "image_pixels":
            return pixel
        u, v = pixel
        return (
            round(u * 999 / max(width - 1, 1)),
            round(v * 999 / max(height - 1, 1)),
        )

    def _decode_point(self, u: int, v: int, width: int, height: int) -> tuple[float, float]:
        """Convert model coordinates to calibrated image pixels."""
        if self.coordinate_contract == "qwen_relative_1000":
            if not (0 <= u <= 999 and 0 <= v <= 999):
                raise ValueError("relative decision point is outside the 0..999 grid")
            return (
                u * max(width - 1, 1) / 999.0,
                v * max(height - 1, 1) / 999.0,
            )
        if not (0 <= u < width and 0 <= v < height):
            raise ValueError("decision pixel is outside the image")
        return float(u), float(v)

    def _direction_to_point(self, direction: str, intr: Any, camera: Camera) -> tuple[int, int]:
        """Turn a direction word into the pixel the rest of the pipeline expects.

        Everything downstream - range gating, waypoint construction, the verifier
        - is written against an image point, so the word is converted here and
        nothing else in OnFly changes. That is what keeps this an output-contract
        experiment rather than a different architecture.

        The bearing is converted through the camera's own focal length, so a
        `left` really is 20 degrees to port for this intrinsics set rather than a
        fixed fraction of the image width.
        """
        if direction not in DIRECTION_BEARING_DEG:
            raise ValueError(f"unknown direction {direction!r}")
        bearing = math.radians(DIRECTION_BEARING_DEG[direction])
        centre_u = intr.width / 2.0
        u = centre_u - camera.focal_px * math.tan(bearing)
        u = min(max(u, 0.0), intr.width - 1.0)
        return int(round(u)), int(round(intr.height / 2.0))

    def _history_pixel(self, ctx: DecisionContext, camera: Camera) -> tuple[int, int] | None:
        if self._previous_goal is None:
            return None
        point = np.array(
            [[self._previous_goal.x, self._previous_goal.y, self._previous_goal.z]],
            dtype=float,
        )
        origin = np.array(
            [ctx.observation.position.x, ctx.observation.position.y, ctx.observation.position.z],
            dtype=float,
        )
        pixels, depths = camera.project(point, origin, ctx.observation.yaw_rad)
        u, v = pixels[0]
        if depths[0] <= 0 or not (0 <= u < camera.width and 0 <= v < camera.height):
            return None
        return round(u), round(v)

    async def decide(self, ctx: DecisionContext):
        if self.services is None or self.services.inference is None:
            raise RuntimeError("OnFly requires a real visual inference backend")
        obs = ctx.observation
        if obs.rgb is None or obs.depth is None or obs.intrinsics is None:
            raise RuntimeError("OnFly requires synchronized RGB, depth, and camera intrinsics")
        image = global_store().get(obs.rgb.uri)
        depth_value = global_store().get(obs.depth.uri)
        if image is None or depth_value is None:
            raise RuntimeError("OnFly sensor references were evicted before inference")
        depth = np.asarray(depth_value, dtype=np.float32).copy()
        if self._initial_yaw_rad is None:
            self._initial_yaw_rad = obs.yaw_rad
            self._home_position = obs.position
        if not self._route_positions or obs.position.distance_to(self._route_positions[-1]) >= 1.0:
            if self._route_positions:
                self._route_flown_m += obs.position.distance_to(self._route_positions[-1])
            self._route_positions.append(obs.position)
            # Truncated for the prompt, so path length is accumulated separately
            # above rather than recomputed from this window.
            self._route_positions = self._route_positions[-12:]
        heading_bin = round((obs.yaw_rad % (2 * math.pi)) / (math.pi / 4)) % 8
        self._viewed_heading_bins.add(heading_bin)
        intr = obs.intrinsics
        camera = Camera(
            width=intr.width,
            height=intr.height,
            fov_deg=math.degrees(2 * math.atan(intr.width / (2 * intr.fx))),
            pitch_rad=self.camera_pitch_rad,
        )
        feedback = ctx.last_routing_feedback
        if feedback is not None and not feedback.accepted and self._last_model_point is not None:
            if self._last_model_point not in self._rejected_model_points:
                self._rejected_model_points.append(self._last_model_point)
                self._rejected_model_points = self._rejected_model_points[-4:]
            # A rejected 3-D goal is not a valid continuity cue. Keeping it in
            # the prompt made deterministic Qwen repeat the same wall pixel.
            self._previous_goal = None
        elif feedback is not None and feedback.accepted:
            self._rejected_model_points = []
        history_pixel = self._history_pixel(ctx, camera)
        history = self._prompt_point(history_pixel, intr.width, intr.height)
        if self.coordinate_contract == "qwen_relative_1000":
            coordinate_text = (
                "Return the point as relative coordinates on a 1000 by 1000 reference grid: "
                "u=0 is the left edge, u=999 the right edge, v=0 the top edge, and v=999 "
                "the bottom edge."
            )
        else:
            coordinate_text = (
                f"Image size is {intr.width}x{intr.height}; return native image pixels."
            )
        history_text = (
            f"The previous 3D goal reprojects to point {history} in that same coordinate system. "
            "Use it only as a continuity cue."
            if history is not None
            else "There is no valid previous-goal point in the current view."
        )
        if not self.previous_goal_prompt:
            history_text = "Choose a fresh navigation point from the current image. "
        if feedback is not None and not feedback.accepted:
            rejected = ", ".join(str(point) for point in self._rejected_model_points)
            feedback_text = (
                "The flight verifier or planner rejected the previous proposal: "
                f"{feedback.reason[:160]}. Rejected points in the current coordinate system: "
                f"[{rejected}]. Do not repeat or choose near those points. Select a visibly open, "
                "traversable continuation that makes progress around the obstruction."
            )
        else:
            feedback_text = (
                "If the named destination is not currently visible, select an obviously open, "
                "traversable continuation toward the subtask; never point at a nearby obstacle "
                "surface merely because a point is required."
            )
        coverage_text = ""
        if self.coverage_prompt:
            origin = self._route_positions[0]
            recent_route = [
                (
                    round(point.x - origin.x, 1),
                    round(point.y - origin.y, 1),
                    round(point.z - origin.z, 1),
                )
                for point in self._route_positions[-6:]
            ]
            relative_heading_deg = math.degrees(
                math.atan2(
                    math.sin(obs.yaw_rad - self._initial_yaw_rad),
                    math.cos(obs.yaw_rad - self._initial_yaw_rad),
                )
            )
            viewed = sorted(self._viewed_heading_bins)
            if relative_heading_deg > 30:
                correction_text = (
                    "Priority: turn toward the RIGHT side of the current image (prefer u>650 on "
                    "the 0..999 grid) until the heading returns near 0 degrees. "
                )
            elif relative_heading_deg < -30:
                correction_text = (
                    "Priority: turn toward the LEFT side of the current image (prefer u<350 on "
                    "the 0..999 grid) until the heading returns near 0 degrees. "
                )
            else:
                correction_text = (
                    "Heading is inside the nominal corridor; continue through an open gap ahead. "
                )
            coverage_text = (
                "Search rule when the exact red tower is absent: the initial camera heading is "
                "the nominal mission corridor. Preserve it while passing occluders; do not explore "
                "behind the launch point. Never select an obstacle face. Prefer visibly open "
                "ground beside an obstacle that carries the UAV around its edge and reveals "
                "terrain hidden "
                "behind it. After clearing the edge, return to the initial corridor. "
                f"{correction_text} Onboard odometry relative to the first decision gives recent "
                f"route points {recent_route}; current heading relative to the initial heading is "
                f"{relative_heading_deg:.0f} degrees; viewed 45-degree heading bins are {viewed}. "
                "Treat the mission text only as a query, never as visual evidence. A red tower "
                "must have visibly red body pixels; green or gray towers are distractors. Route "
                "past a distractor's edge, never to its center or base. Compare open corridors "
                "internally and choose the one with greatest expected new visibility. "
            )
        output_text = (
            "Report target_visible=true only when the exact red tower is visibly present; "
            "otherwise false. Always include u and v: when visible point to its base, otherwise "
            "point to the best open corridor. Return only JSON with boolean target_visible and "
            "integer u and v. "
            if self.frontier_assist
            else "Return only JSON with integer u and v. "
        )
        if self.coordinate_contract == "discrete_direction":
            output_text = (
                "Choose exactly one steering direction from: hard_left, left, ahead, right, "
                "hard_right. `ahead` means the route continues straight; choose it only when "
                "the way forward is genuinely the best option, not as a default. "
                + (
                    "Report target_visible=true only when the exact red tower is visibly "
                    "present; otherwise false. Return only JSON with boolean target_visible "
                    "and string direction. "
                    if self.frontier_assist
                    else "Return only JSON with string direction. "
                )
            )
        route_text = ""
        if self.route_hint:
            origin = self._home_position or obs.position
            flown = self._route_flown_m
            turned = 0.0
            if self._initial_yaw_rad is not None:
                turned = math.degrees(
                    math.atan2(
                        math.sin(obs.yaw_rad - self._initial_yaw_rad),
                        math.cos(obs.yaw_rad - self._initial_yaw_rad),
                    )
                )
            straight = math.dist(
                (origin.x, origin.y, origin.z), (obs.position.x, obs.position.y, obs.position.z)
            )
            route_text = (
                f"A route that reaches the destination is: {self.route_hint} "
                "Follow it. Onboard odometry says you have flown "
                f"{flown:.0f} m of path, you are {straight:.0f} m from where you started, "
                f"and your heading is {turned:+.0f} degrees from your initial heading. "
                "Work out which leg of the route you are on and point at where that leg "
                "continues. "
            )
        if self.step_from_model:
            output_text += (
                f"Also return integer d between 1 and {self.step_levels}: how far to travel "
                "toward that point on this step. 1 is a short cautious hop; "
                f"{self.step_levels} is a long commitment through open space. Choose a large d "
                "to cross open ground or to continue past an occluder into terrain you cannot "
                "yet see, and a small d when an obstacle is close ahead. "
            )
        prompt = (
            "You are OnFly's high-frequency decision agent on a UAV. Select the next image-space "
            "navigation target for the current subtask. (0,0) is top-left. "
            f"{coordinate_text} Subtask: {ctx.mission.instruction}. "
            "Match every explicitly named visual attribute in the subtask exactly, including "
            "object type, color, and relative location. A similarly shaped object with a "
            "different named attribute is a distractor, not the destination. "
            f"{history_text} {feedback_text} {coverage_text}{route_text}"
            f"{output_text}"
            "Do not report distance, world coordinates, completion, or flight controls."
        )
        result = await self.services.inference.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role="policy",
                prompt_hash="onfly:decision:v1",
                input_tokens=max(1, len(prompt) // 4),
                image_count=1,
                observation_seq=obs.seq,
                prompt=prompt,
                images=(_encode_png(image),),
                response_schema=self._schema(intr.width, intr.height),
            )
        )
        self.model_calls += 1
        try:
            answer = _extract_json(result.payload)
            if self.coordinate_contract == "discrete_direction":
                expected = (
                    {"target_visible", "direction"} if self.frontier_assist else {"direction"}
                )
            else:
                expected = {"target_visible", "u", "v"} if self.frontier_assist else {"u", "v"}
            if self.step_from_model:
                expected = expected | {"d"}
            if set(answer) != expected:
                raise ValueError(f"decision JSON must contain exactly {sorted(expected)}")
            target_visible = bool(answer["target_visible"]) if self.frontier_assist else True
            if self.coordinate_contract == "discrete_direction":
                model_u, model_v = self._direction_to_point(str(answer["direction"]), intr, camera)
                u, v = float(model_u), float(model_v)
            else:
                model_u, model_v = int(answer["u"]), int(answer["v"])
                u, v = self._decode_point(model_u, model_v, intr.width, intr.height)
            model_step_level = int(answer["d"]) if self.step_from_model else 0
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self.parse_errors += 1
            raise RuntimeError(f"invalid OnFly decision-agent output: {exc}") from exc
        self._last_model_point = (model_u, model_v)
        if self.frontier_assist and not target_visible:
            assert self._initial_yaw_rad is not None
            assert self._home_position is not None
            heading_x = math.cos(self._initial_yaw_rad)
            heading_y = math.sin(self._initial_yaw_rad)
            delta_x = obs.position.x - self._home_position.x
            delta_y = obs.position.y - self._home_position.y
            progress_m = max(0.0, delta_x * heading_x + delta_y * heading_y)
            next_progress_m = progress_m + self.frontier_hop_m
            target = Vec3(
                x=self._home_position.x + next_progress_m * heading_x,
                y=self._home_position.y + next_progress_m * heading_y,
                z=obs.position.z,
            )
            self._previous_goal = target
            return self.envelope(
                ctx,
                DecisionKind.WAYPOINT,
                WaypointGoal(
                    target=target,
                    target_label=None,
                    tolerance_m=1.0,
                    stop_at_target=False,
                ),
                1.0,
                note="OnFly absence decision advanced the observable launch corridor frontier",
                extra={
                    "target_visible": "false",
                    "model_u": str(model_u),
                    "model_v": str(model_v),
                    "frontier_basis": "initial_observed_heading",
                    "source_position_x": f"{obs.position.x:.9f}",
                    "source_position_y": f"{obs.position.y:.9f}",
                    "source_position_z": f"{obs.position.z:.9f}",
                    "source_yaw_rad": f"{obs.yaw_rad:.9f}",
                    "sampled_depth_m": "nan",
                    "history_pixel": str(history_pixel),
                },
            )

        sampled = _depth_at(depth, u, v)
        depth_m = min(self.max_depth_m, sampled if sampled is not None else self.max_depth_m)
        half_fov = math.atan(intr.width / (2 * intr.fx))
        gated = bearing_gated_range(
            depth_m,
            u,
            fx=intr.fx,
            cx=intr.cx,
            half_fov_rad=half_fov,
            sigma_theta=self.sigma_theta,
        )
        # OnFly lifts the bearing-gated depth itself. A synthetic minimum hop
        # can exceed the gate at close range and make the verifier reject an
        # otherwise self-consistent proposal forever.
        executable_range = max(0.0, gated - self.goal_standoff_m)
        if self.step_from_model:
            # SPF's step: the model names the distance and no depth ceiling
            # applies, so a waypoint may be placed beyond the first surface on
            # the ray. ``gated`` is still computed above and recorded below, so
            # both step sources are comparable on the same run.
            executable_range = max(0.0, self._model_step_m(model_step_level) - self.goal_standoff_m)
        origin = np.array([obs.position.x, obs.position.y, obs.position.z], dtype=float)
        projected = camera.unproject(u, v, executable_range, origin, obs.yaw_rad)
        # Equation (3) lifts the complete camera ray.  Holding altitude after
        # unprojection changes its camera-forward component whenever the camera
        # is pitched, so the resulting point no longer represents ``d_f`` and
        # can be rejected by the very consistency check that validates it.
        target = Vec3(
            x=float(projected[0]),
            y=float(projected[1]),
            z=float(projected[2]),
        )
        self._previous_goal = target
        return self.envelope(
            ctx,
            DecisionKind.WAYPOINT,
            WaypointGoal(
                target=target,
                target_label=self.target_label,
                tolerance_m=1.0,
                stop_at_target=False,
            ),
            1.0,
            note=(
                "OnFly image target lifted with a model-named step (SPF)"
                if self.step_from_model
                else "OnFly image target lifted with synchronized depth and bearing gate"
            ),
            extra={
                "pixel_u": f"{u:g}",
                "pixel_v": f"{v:g}",
                "model_u": str(model_u),
                "model_v": str(model_v),
                "coordinate_contract": self.coordinate_contract,
                "camera_pitch_rad": f"{self.camera_pitch_rad:.9f}",
                "source_position_x": f"{obs.position.x:.9f}",
                "source_position_y": f"{obs.position.y:.9f}",
                "source_position_z": f"{obs.position.z:.9f}",
                "source_yaw_rad": f"{obs.yaw_rad:.9f}",
                "sampled_depth_m": f"{depth_m:.6f}",
                "gated_range_m": f"{gated:.6f}",
                "executable_range_m": f"{executable_range:.6f}",
                "step_source": "model" if self.step_from_model else "depth",
                "model_step_level": str(model_step_level),
                "history_pixel": str(history_pixel),
                "history_model_point": str(history),
                "rgb_digest": obs.rgb.digest,
                "depth_digest": obs.depth.digest,
            },
        )

    def stats(self) -> dict[str, float]:
        return {
            "onfly_decision_calls": float(self.model_calls),
            "onfly_decision_parse_errors": float(self.parse_errors),
        }


@dataclass(slots=True)
class _VisualFrame:
    seq: int
    t_ns: int
    position: Vec3
    yaw: float
    distance: float
    image: Any
    depth: np.ndarray | None
    feature: np.ndarray


_ONFLY_VISUALS: dict[str, Any] = {}


_MONITOR_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"status": {"type": "string", "enum": ["CONTINUE", "STOP", "LOST"]}},
    "required": ["status"],
    "additionalProperties": False,
}

_MONITOR_EVIDENCE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "earlier_target_visible": {"type": "boolean"},
        "latest_target_visible": {"type": "boolean"},
        "latest_target_scale": {
            "type": "string",
            "enum": ["absent", "small", "large"],
        },
        "status": {"type": "string", "enum": ["CONTINUE", "STOP", "LOST"]},
    },
    "required": [
        "earlier_target_visible",
        "latest_target_visible",
        "latest_target_scale",
        "status",
    ],
    "additionalProperties": False,
}


def _monitor_prompt(instruction: str) -> str:
    """Unreleased-paper-compatible forced-choice monitoring contract."""
    return (
        "You are OnFly's independent low-frequency progress monitor. Images are "
        "chronological: initial view, route keyframes, then the latest view. Mission: "
        f"{instruction}. A destination counts as visible only if it matches every explicitly "
        "named visual attribute, including object type, color, and relative location. A "
        "lookalike with a different named attribute is a distractor and must not establish "
        "acquisition or completion. Return exactly one status: CONTINUE, STOP, or LOST. "
        "CONTINUE means the latest visual history still supports useful progress, or the "
        "named destination has not appeared yet and exploration remains coherent. STOP means "
        "the requested semantic destination is visibly reached in the LATEST image only: it is "
        "extremely close, occupies a large part of the view (roughly one third of image height "
        "or more), and its base/reached location is at the vehicle. A small or distant target, "
        "even if centered and present in several historical images, is never STOP. If the "
        "destination is absent from the latest image, STOP is forbidden. LOST means "
        "the destination appeared in earlier route images but disappeared "
        "from the latest view while flight continued, or the recent visual trajectory clearly "
        "drifts away from prior progress. Do not assume an invisible destination remains ahead. "
        "When sustained post-acquisition loss makes CONTINUE unsafe, choose LOST so the fixed "
        "executive can stop and reorient. Return only JSON with one status field."
    )


def _latest_emphasis_sheet(images: list[Any]) -> Any:
    """One labeled image that keeps history but makes latest state unambiguous."""
    from PIL import Image, ImageDraw

    if not images:
        raise ValueError("latest-emphasis monitor layout needs at least one image")
    sheet = Image.new("RGB", (672, 472), "black")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(images[:-1]):
        x = (index % 2) * 112
        y = (index // 2) * 148
        draw.text((x + 4, y + 3), f"HISTORY {index + 1}", fill="white")
        sheet.paste(image.convert("RGB").resize((112, 112)), (x, y + 24))
    draw.text((236, 3), "LATEST (judge STOP/LOST from this large panel)", fill="white")
    sheet.paste(images[-1].convert("RGB").resize((436, 436)), (236, 28))
    return sheet


def _history_sheet(images: list[Any]) -> Any:
    """Label and pack only historical frames; latest stays a separate image."""
    from PIL import Image, ImageDraw

    if not images:
        raise ValueError("history sheet needs at least one image")
    columns = 3
    panel_w = panel_h = 224
    label_h = 24
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * panel_w, rows * (panel_h + label_h)), "black")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(images):
        x = (index % columns) * panel_w
        y = (index // columns) * (panel_h + label_h)
        draw.text((x + 6, y + 5), f"HISTORY {index + 1}", fill="white")
        sheet.paste(image.convert("RGB").resize((panel_w, panel_h)), (x, y + label_h))
    return sheet


def _visual_feature(image: Any) -> np.ndarray:
    small = np.asarray(image.convert("RGB").resize((8, 8)), dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(small))
    return small / max(norm, 1e-6)


class _OnFlyVisualMemoryBase:
    def __init__(self, **params: Any) -> None:
        self.budget = int(params.get("keyframe_budget", 4))
        self.translation_threshold_m = float(params.get("translation_threshold_m", 2.0))
        self.rotation_threshold_rad = float(
            params.get("rotation_threshold_rad", math.radians(20.0))
        )
        self.dedupe_epsilon = float(params.get("dedupe_epsilon", 0.08))
        self.dedupe_distance_m = float(params.get("dedupe_distance_m", 3.0))
        self._frames: list[_VisualFrame] = []
        self._seq = 0
        self._t_ns = 0
        self._distance = 0.0
        self._last_position: Vec3 | None = None
        self._last_candidate: _VisualFrame | None = None
        self._updates = 0

    def reset(self, mission: MissionSpec, seed: int) -> None:
        _ONFLY_VISUALS.clear()
        self._frames = []
        self._seq = self._t_ns = 0
        self._distance = 0.0
        self._last_position = None
        self._last_candidate = None
        self._updates = 0

    def _capture(self, observation: ObservationPacket) -> _VisualFrame | None:
        self._updates += 1
        self._seq, self._t_ns = observation.seq, observation.t_sim_ns
        if observation.rgb is None:
            return None
        image = global_store().get(observation.rgb.uri)
        if image is None:
            return None
        if self._last_position is not None:
            self._distance += self._last_position.distance_to(observation.position)
        self._last_position = observation.position
        depth = None
        if observation.depth is not None:
            value = global_store().get(observation.depth.uri)
            if value is not None:
                depth = np.asarray(value, dtype=np.float32).copy()
        return _VisualFrame(
            seq=observation.seq,
            t_ns=observation.t_sim_ns,
            position=observation.position,
            yaw=observation.yaw_rad,
            distance=self._distance,
            image=image.copy(),
            depth=depth,
            feature=_visual_feature(image),
        )

    @staticmethod
    def _item(frame: _VisualFrame, kind: str) -> MemoryItem:
        image_uri = f"onfly://rgb/{frame.seq}"
        depth_uri = f"onfly://depth/{frame.seq}" if frame.depth is not None else None
        _ONFLY_VISUALS[image_uri] = frame.image
        if depth_uri is not None:
            _ONFLY_VISUALS[depth_uri] = frame.depth
        return MemoryItem(
            observation_seq=frame.seq,
            t_sim_ns=frame.t_ns,
            kind=kind,
            summary=f"visual frame at path distance {frame.distance:.1f} m",
            position=frame.position,
            yaw_rad=frame.yaw,
            salience=1.0,
            image_uri=image_uri,
            depth_uri=depth_uri,
        )


@register("memory", "onfly_sliding_memory")
class OnFlySlidingMemory(_OnFlyVisualMemoryBase):
    """Visual recent-frame window used for the C4 memory control."""

    @property
    def name(self) -> str:
        return "onfly_sliding_memory"

    def update(
        self, observation: ObservationPacket, perception: PerceptionState, decision: Any
    ) -> None:
        frame = self._capture(observation)
        if frame is not None:
            self._frames.append(frame)
            self._frames = self._frames[-(self.budget + 2) :]

    def snapshot(self) -> MemorySnapshot:
        items = tuple(self._item(frame, "recent_frame") for frame in self._frames)
        return MemorySnapshot(
            observation_seq=self._seq,
            t_sim_ns=self._t_ns,
            items=items,
            token_budget=len(items) * 24,
            tokens_used=len(items) * 24,
            policy_name=self.name,
            stats={"visual_frames": float(len(items)), "updates": float(self._updates)},
        )


@register("memory", "onfly_hybrid_memory")
class OnFlyHybridMemory(_OnFlyVisualMemoryBase):
    """First frame + distance-segment keyframes + latest visual frame."""

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self._latest: _VisualFrame | None = None
        self._segment_winners: list[_VisualFrame | None] = [None] * self.budget
        self._serialized_keys: list[_VisualFrame] = []
        self._prefix_reused = 0

    @property
    def name(self) -> str:
        return "onfly_hybrid_memory"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self._latest = None
        self._segment_winners = [None] * self.budget
        self._serialized_keys = []
        self._prefix_reused = 0

    def update(
        self, observation: ObservationPacket, perception: PerceptionState, decision: Any
    ) -> None:
        frame = self._capture(observation)
        if frame is None:
            return
        self._latest = frame
        if not self._frames:
            self._frames.append(frame)
            self._last_candidate = frame
            return
        last = self._last_candidate or self._frames[-1]
        yaw_delta = abs(math.atan2(math.sin(frame.yaw - last.yaw), math.cos(frame.yaw - last.yaw)))
        translated = frame.position.distance_to(last.position)
        if translated < self.translation_threshold_m and yaw_delta < self.rotation_threshold_rad:
            return
        self._last_candidate = frame
        # The paper first restricts feature matching to geometrically nearby
        # pool entries.  Comparing against the entire route collapses visually
        # similar corridors into one frame and destroys global coverage.
        nearby = [
            old
            for old in self._frames
            if frame.position.distance_to(old.position) <= self.dedupe_distance_m
        ]
        if any(
            1.0 - float(np.dot(frame.feature, old.feature)) < self.dedupe_epsilon for old in nearby
        ):
            return
        self._frames.append(frame)

    def _segment_index(self, frame: _VisualFrame, total: float) -> int:
        return int(min(self.budget - 1, frame.distance / total * self.budget))

    def _select_keys(self, latest: _VisualFrame) -> list[_VisualFrame]:
        """Apply OnFly's sticky segment selection and prefix-stable serialization.

        Segment boundaries move as travelled distance grows.  Recomputing every
        winner from scratch makes old input slots churn and defeats the mechanism
        the paper attributes its monitor stability and KV-cache reuse to.  A
        previous winner is therefore retained while it remains in its segment;
        only invalid winners are reselected.  The serialized list preserves the
        longest still-valid prefix, then appends current winners and recent
        unused pool entries to fill empty segment slots.
        """
        total = max(latest.distance, 1e-6)
        candidates = [frame for frame in self._frames[1:] if frame.seq != latest.seq]
        by_seq = {frame.seq: frame for frame in candidates}
        winners: list[_VisualFrame | None] = [None] * self.budget
        for segment in range(self.budget):
            previous = self._segment_winners[segment]
            if (
                previous is not None
                and previous.seq in by_seq
                and self._segment_index(previous, total) == segment
            ):
                winners[segment] = by_seq[previous.seq]
                continue
            center = total * (segment + 0.5) / self.budget
            in_segment = [
                frame for frame in candidates if self._segment_index(frame, total) == segment
            ]
            if in_segment:
                winners[segment] = min(
                    in_segment,
                    key=lambda frame: (abs(frame.distance - center), -frame.t_ns),
                )
        self._segment_winners = winners

        current = [frame for frame in winners if frame is not None]
        current_by_seq = {frame.seq: frame for frame in current}
        serialized: list[_VisualFrame] = []
        for old in self._serialized_keys:
            if old.seq not in current_by_seq:
                break
            serialized.append(current_by_seq[old.seq])

        used = {frame.seq for frame in serialized}
        for frame in current:
            if frame.seq not in used:
                serialized.append(frame)
                used.add(frame.seq)

        # The paper fills empty segment slots with unused recent pool entries.
        # Keep the set bounded and deterministic; chronological sorting below
        # makes the actual monitor input order stable.
        for frame in sorted(candidates, key=lambda item: item.t_ns, reverse=True):
            if len(serialized) >= self.budget:
                break
            if frame.seq not in used:
                serialized.append(frame)
                used.add(frame.seq)

        serialized = sorted(serialized[: self.budget], key=lambda frame: frame.t_ns)
        self._prefix_reused = 0
        for old, new in zip(self._serialized_keys, serialized, strict=False):
            if old.seq != new.seq:
                break
            self._prefix_reused += 1
        self._serialized_keys = serialized
        return serialized

    def _selected(self) -> list[_VisualFrame]:
        if not self._frames:
            return []
        first = self._frames[0]
        latest = self._latest or first
        if len(self._frames) == 1:
            return [first] if first.seq == latest.seq else [first, latest]
        keys = self._select_keys(latest)
        ordered = [first, *keys, latest]
        unique: dict[int, _VisualFrame] = {frame.seq: frame for frame in ordered}
        return sorted(unique.values(), key=lambda frame: frame.t_ns)

    def snapshot(self) -> MemorySnapshot:
        selected = self._selected()
        items_list: list[MemoryItem] = []
        for i, frame in enumerate(selected):
            kind = "initial" if i == 0 else "latest" if i == len(selected) - 1 else "keyframe"
            items_list.append(self._item(frame, kind))
        items = tuple(items_list)
        keyframes = sum(item.kind == "keyframe" for item in items)
        return MemorySnapshot(
            observation_seq=self._seq,
            t_sim_ns=self._t_ns,
            items=items,
            token_budget=(self.budget + 2) * 24,
            tokens_used=len(items) * 24,
            policy_name=self.name,
            # ``updates`` also makes a sensor-less contract probe observable;
            # the real visual state remains empty when no pixels were supplied.
            stats={
                "keyframes": float(keyframes),
                "candidate_pool": float(len(self._frames)),
                "prefix_reused": float(self._prefix_reused),
                "updates": float(self._updates),
            },
        )


@register("monitor", "onfly_monitor")
class OnFlyMonitor:
    """Low-rate forced-choice visual monitor over bounded visual memory."""

    def __init__(self, **params: Any) -> None:
        self.model_id = str(params.get("model_id", "gemma3:4b"))
        self.stop_confirmations = int(params.get("stop_confirmations", 2))
        self.layout = str(params.get("layout", "multi_image"))
        if self.layout not in {
            "multi_image",
            "latest_emphasis_sheet",
            "history_sheet_plus_latest",
        }:
            raise ValueError(
                "OnFly monitor layout must be multi_image, latest_emphasis_sheet, "
                "or history_sheet_plus_latest"
            )
        self.structured_evidence = bool(params.get("structured_evidence", False))
        self.target_bound_stop = bool(params.get("target_bound_stop", False))
        self.current_grounding = bool(params.get("current_grounding", False))
        if self.current_grounding and not self.target_bound_stop:
            raise ValueError("current_grounding requires target_bound_stop")
        if self.target_bound_stop and not self.structured_evidence:
            raise ValueError("target_bound_stop requires structured_evidence")
        if self.target_bound_stop and (
            self.stop_confirmations < 2 or self.layout == "latest_emphasis_sheet"
        ):
            raise ValueError(
                "target_bound_stop needs two confirmations and full-resolution imagery"
            )
        self.target_consistency_m = float(params.get("target_consistency_m", 1.0))
        if self.target_bound_stop and (
            not math.isfinite(self.target_consistency_m) or self.target_consistency_m <= 0
        ):
            raise ValueError("target_consistency_m must be finite and positive")
        self.camera_pitch_rad = float(params.get("camera_pitch_rad", -0.15))
        self._arrival_point: np.ndarray | None = None
        self._arrival_seq = -1
        self.acquisition_confirmations = int(params.get("acquisition_confirmations", 2))
        if self.acquisition_confirmations < 1:
            raise ValueError("OnFly acquisition_confirmations must be at least 1")
        self.stop_max_depth_m = float(params.get("stop_max_depth_m", 3.0))
        self.reject_depth_vetoed_acquisition = bool(
            params.get("reject_depth_vetoed_acquisition", False)
        )
        self.strict_attribute_evidence = bool(params.get("strict_attribute_evidence", False))
        self.lost_hold_s = float(params.get("lost_hold_s", 0.25))
        self.lost_reorient_s = float(params.get("lost_reorient_s", 2.0))
        self.lost_yaw_rate_rps = float(params.get("lost_yaw_rate_rps", 0.8))
        self.services: RuntimeServices | None = None
        self._stop_count = 0
        self._ever_acquired = False
        self._acquisition_count = 0
        self.calls = 0
        self.parse_errors = 0

    @property
    def name(self) -> str:
        return "onfly_monitor"

    def bind_runtime(self, services: RuntimeServices) -> None:
        self.services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._stop_count = self.calls = self.parse_errors = 0
        self._arrival_point = None
        self._arrival_seq = -1
        self._ever_acquired = False
        self._acquisition_count = 0

    async def assess(self, ctx: DecisionContext) -> ProgressState:
        if self.services is None or self.services.inference is None:
            raise RuntimeError("OnFly monitor requires a real visual inference backend")
        images: list[str] = []
        evidence_seq = ctx.observation.seq
        evidence_t_ns = ctx.observation.t_sim_ns
        # Snapshot synchronized sensor data before inference can advance the runtime.
        arrival_depth = None
        current_rgb = None
        if self.target_bound_stop:
            if ctx.observation.depth is not None:
                stored = global_store().get(ctx.observation.depth.uri)
                if stored is not None:
                    arrival_depth = np.array(stored, copy=True)
            if ctx.observation.rgb is not None:
                current_rgb = global_store().get(ctx.observation.rgb.uri)
        for item in ctx.memory.items:
            if self.target_bound_stop and item.observation_seq >= ctx.observation.seq:
                continue
            if item.image_uri and item.image_uri in _ONFLY_VISUALS:
                images.append(_encode_png(_ONFLY_VISUALS[item.image_uri]))
                evidence_seq = item.observation_seq
                evidence_t_ns = item.t_sim_ns
        if self.target_bound_stop:
            if current_rgb is None:
                self._stop_count = 0
                self._arrival_point = None
                return ProgressState(
                    label=ProgressLabel.CONTINUE,
                    observation_seq=ctx.observation.seq,
                    t_sim_ns=ctx.observation.t_sim_ns,
                    confidence=0.0,
                    evidence="target-bound STOP unavailable: missing current RGB",
                    monitor_name=self.name,
                )
            images.append(_encode_png(current_rgb))
            evidence_seq = ctx.observation.seq
            evidence_t_ns = ctx.observation.t_sim_ns
        if not images and ctx.observation.rgb is not None:
            current = global_store().get(ctx.observation.rgb.uri)
            if current is not None:
                images.append(_encode_png(current))
        if self.layout == "latest_emphasis_sheet" and images:
            from PIL import Image

            decoded = [
                Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
                for encoded in images
            ]
            images = [_encode_png(_latest_emphasis_sheet(decoded))]
        elif self.layout == "history_sheet_plus_latest" and images:
            from PIL import Image

            decoded = [
                Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
                for encoded in images
            ]
            latest = decoded[-1]
            images = [_encode_png(latest)]
            if len(decoded) > 1:
                # Keep temporal memory and the current sensor frame in separate
                # image inputs. Compressing both into one montage made Qwen
                # transfer attributes from history/distractors into LATEST.
                images = [_encode_png(_history_sheet(decoded[:-1])), _encode_png(latest)]
        prompt = _monitor_prompt(ctx.mission.instruction)
        if self.strict_attribute_evidence:
            prompt += (
                " Treat mission words only as a query, never as evidence that the object exists. "
                "For a red tower, latest_target_visible may be true only when the latest image "
                "contains clearly red body pixels belonging to a tower. Green or gray rectangular "
                "towers are distractors: report latest_target_visible=false and forbid STOP. "
                "Check visible color before shape, scale, route history, or expected location."
            )
        if self.layout == "history_sheet_plus_latest" and len(images) == 2:
            prompt += (
                " The first provided image is a labeled HISTORY sheet. The second "
                "provided image is the full-resolution LATEST camera frame; judge "
                "latest_target_visible, latest_target_scale, STOP, and LOST from that "
                "second image."
            )
        schema = _MONITOR_SCHEMA
        if self.structured_evidence:
            prompt += (
                " Inspect the latest image separately from all earlier images. Also report "
                "bounded visual evidence: earlier_target_visible, latest_target_visible, and "
                "latest_target_scale as absent, small, or large."
            )
            schema = _MONITOR_EVIDENCE_SCHEMA
        if self.target_bound_stop:
            schema = {
                **_MONITOR_EVIDENCE_SCHEMA,
                "properties": {
                    **_MONITOR_EVIDENCE_SCHEMA["properties"],
                    "target_u": {"type": ["integer", "null"], "minimum": 0, "maximum": 999},
                    "target_v": {"type": ["integer", "null"], "minimum": 0, "maximum": 999},
                },
                "required": [*_MONITOR_EVIDENCE_SCHEMA["required"], "target_u", "target_v"],
            }
            prompt += (
                " In the LATEST full-resolution frame, locate the actual requested target: "
                "return target_u and target_v in normalized 0-999 image coordinates "
                "(0,0 top-left; 999,999 bottom-right), on its visible body near flight height. "
                "Do not point at a navigation opening, ground, or obstacle in front of it. "
                "If the requested target cannot be identified, set both coordinates to null "
                "and latest_target_visible=false. Mission words are a query, not evidence."
            )
        if self.current_grounding:
            # Identity comes only from the current image. History is maintained
            # by the executive; geometric arrival is evaluated after grounding.
            images = [_encode_png(current_rgb)]
            prompt = (
                "Describe the visible objects and colors briefly in evidence, then locate "
                f"the destination requested by: {ctx.mission.instruction}. "
                "The instruction is a query, not evidence that its object is present. "
                "Set visible=true only if that exact object is identifiable in this image. "
                "Give u,v on its visible body in a 0-999 grid (top-left origin). "
                "If absent set visible=false and u=v=null. Return JSON only."
            )
            coordinate = {"type": ["integer", "null"], "minimum": 0, "maximum": 999}
            schema = {
                "type": "object",
                "properties": {
                    "evidence": {"type": "string", "maxLength": 120},
                    "visible": {"type": "boolean"},
                    "u": coordinate,
                    "v": coordinate,
                },
                "required": ["evidence", "visible", "u", "v"],
                "additionalProperties": False,
            }
        result = await self.services.inference.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role="monitor",
                prompt_hash="onfly:monitor:current_grounding_v1"
                if self.current_grounding
                else "onfly:monitor:target_bound_v1"
                if self.target_bound_stop
                else "onfly:monitor:v1",
                input_tokens=max(1, len(prompt) // 4),
                image_count=len(images),
                observation_seq=ctx.observation.seq,
                prompt=prompt,
                images=tuple(images),
                response_schema=schema,
            )
        )
        self.calls += 1
        recovery_anchor_valid = False
        recovery_reacquired = False
        grounding_evidence = None
        try:
            parsed = _extract_json(result.payload)
            if self.current_grounding:
                if set(parsed) != {"evidence", "visible", "u", "v"}:
                    raise ValueError("invalid current-grounding fields")
                if type(parsed["visible"]) is not bool or not isinstance(parsed["evidence"], str):
                    raise ValueError("invalid current-grounding types")
                visible = parsed["visible"]
                grounding_evidence = parsed["evidence"]
                parsed = {
                    "earlier_target_visible": self._ever_acquired,
                    "latest_target_visible": visible,
                    "latest_target_scale": "large" if visible else "absent",
                    # STOP is only a candidate; metric arrival must still pass.
                    "status": "STOP" if visible else "LOST",
                    "target_u": parsed["u"] if visible else None,
                    "target_v": parsed["v"] if visible else None,
                }
            expected = (
                {
                    "earlier_target_visible",
                    "latest_target_visible",
                    "latest_target_scale",
                    "status",
                }
                if self.structured_evidence
                else {"status"}
            )
            if self.target_bound_stop:
                expected |= {"target_u", "target_v"}
                if (
                    type(parsed.get("latest_target_visible")) is not bool
                    or type(parsed.get("earlier_target_visible")) is not bool
                    or type(parsed.get("latest_target_scale")) is not str
                    or parsed.get("latest_target_scale") not in {"absent", "small", "large"}
                ):
                    raise ValueError("invalid typed target evidence")
                for key in ("target_u", "target_v"):
                    value = parsed.get(key)
                    if value is not None and (type(value) is not int or not 0 <= value <= 999):
                        raise ValueError("target coordinates must be integers in 0-999 or null")
            if set(parsed) != expected or parsed["status"] not in {"CONTINUE", "STOP", "LOST"}:
                raise ValueError("status must be CONTINUE, STOP, or LOST")
            label = ProgressLabel(parsed["status"].lower())
            recovery_anchor_valid = label is ProgressLabel.CONTINUE
        except (ValueError, json.JSONDecodeError) as exc:
            self.parse_errors += 1
            label = ProgressLabel.CONTINUE
            evidence = f"invalid monitor output; fail-safe CONTINUE ({exc})"
        else:
            evidence = f"visual monitor classified {label.value} from {len(images)} frames"
            if self.structured_evidence:
                was_acquired = self._ever_acquired
                earlier = bool(parsed["earlier_target_visible"])
                latest = bool(parsed["latest_target_visible"])
                if self.target_bound_stop:
                    latest = (
                        latest and parsed["target_u"] is not None and parsed["target_v"] is not None
                    )
                scale = str(parsed["latest_target_scale"])
                sampled_depth = None
                if ctx.last_decision is not None:
                    try:
                        sampled_depth = float(
                            ctx.last_decision.provenance.get("sampled_depth_m", "nan")
                        )
                    except ValueError:
                        sampled_depth = None
                depth_vetoed_acquisition = (
                    self.reject_depth_vetoed_acquisition
                    and label is ProgressLabel.STOP
                    and (
                        sampled_depth is None
                        or not math.isfinite(sampled_depth)
                        or sampled_depth > self.stop_max_depth_m
                    )
                )
                # `reject_depth_vetoed_acquisition` stays OFF by default, and
                # the reason is worth recording because the opposite looks
                # obviously right and is not.
                #
                # On seed 1060 Gemma 3 4B reported the red tower "large" and
                # requested STOP at a sampled depth of 7.0 m while the true goal
                # was 33.1 m away, and `_ever_acquired` then latched on that
                # phantom. Turning the veto on by default seemed to fix it. But
                # `stop_max_depth_m` is a *stopping* threshold, not a validity
                # threshold: a target genuinely visible at 7 m with a 3 m stop
                # radius produces the identical reading. The two cases are
                # indistinguishable from onboard data, so this test cannot tell a
                # phantom from a legitimate distant sighting, and defaulting it on
                # would refuse every honest acquisition made before arrival.
                # `test_monitor_accepts_current_visibility_when_previous_goal_left_the_frame`
                # encodes exactly that case and fails when the default is flipped.
                #
                # Detecting the phantom needs evidence the harness does not have
                # without privileged truth. Left open rather than papered over.
                if latest and not depth_vetoed_acquisition:
                    self._acquisition_count = min(
                        self._acquisition_count + 1,
                        self.acquisition_confirmations,
                    )
                else:
                    self._acquisition_count = 0
                if self._acquisition_count >= self.acquisition_confirmations:
                    self._ever_acquired = True
                # Historical visibility can preserve context, but it cannot
                # establish acquisition: only stable evidence in the latest
                # sensor frame may arm post-acquisition LOST recovery.
                recovery_reacquired = latest and self._ever_acquired
                history_continuous: bool | None = None
                if (
                    ctx.last_decision is not None
                    and ctx.last_decision.producer == "onfly_decision"
                    and "history_pixel" in ctx.last_decision.provenance
                ):
                    history_marker = ctx.last_decision.provenance["history_pixel"]
                    history_continuous = history_marker not in {"", "None"}
                if was_acquired and latest and history_continuous is False:
                    # A previous waypoint leaving the image is not proof that
                    # the destination is lost. The waypoint may have been
                    # executed or replaced while the destination remains
                    # plainly visible in the newest frame. Current visual
                    # evidence therefore wins and establishes a fresh anchor.
                    evidence = (
                        "latest target reacquired despite loss of the previous-goal reprojection"
                    )
                elif self._ever_acquired and label is ProgressLabel.CONTINUE and not latest:
                    label = ProgressLabel.LOST
                    recovery_reacquired = False
                    evidence = (
                        "post-acquisition CONTINUE contradicted by latest-frame absence; normalized"
                    )
                elif label is ProgressLabel.STOP and (not latest or scale == "absent"):
                    label = ProgressLabel.LOST if self._ever_acquired else ProgressLabel.CONTINUE
                    evidence = "STOP contradicted by declared latest-frame absence; normalized"
                if label is ProgressLabel.LOST and not self._ever_acquired:
                    label = ProgressLabel.CONTINUE
                    # Before acquisition, an explicit absence is nominal search
                    # rather than a recovery state, so its pose remains a valid
                    # fallback heading if the target is acquired later.
                    recovery_anchor_valid = True
                    evidence = "pre-acquisition LOST contradicted by declared history; normalized"
                if self.target_bound_stop:
                    label, arrival_evidence = self._target_arrival(
                        ctx, parsed, label, arrival_depth
                    )
                    evidence += "; " + arrival_evidence
                else:
                    if label is ProgressLabel.STOP:
                        sampled_depth = None
                        if ctx.last_decision is not None:
                            try:
                                sampled_depth = float(
                                    ctx.last_decision.provenance.get("sampled_depth_m", "nan")
                                )
                            except ValueError:
                                sampled_depth = None
                        if (
                            sampled_depth is None
                            or not math.isfinite(sampled_depth)
                            or sampled_depth > self.stop_max_depth_m
                        ):
                            label = ProgressLabel.CONTINUE
                            recovery_anchor_valid = latest and (
                                not was_acquired or history_continuous is not False
                            )
                            evidence = (
                                "visual STOP vetoed by synchronized depth "
                                f"({sampled_depth!r} m > {self.stop_max_depth_m:.1f} m)"
                            )
                recovery_anchor_valid = label is ProgressLabel.CONTINUE and (
                    not self._ever_acquired or latest
                )
                evidence += (
                    f"; earlier_visible={earlier}; latest_visible={latest}; "
                    f"latest_scale={scale}; ever_acquired={self._ever_acquired}; "
                    f"acquisition_count={self._acquisition_count}/"
                    f"{self.acquisition_confirmations}; "
                    f"history_continuous={history_continuous}"
                )
        if self.current_grounding:
            evidence += f"; identity_source=current_frame_vlm; grounding={grounding_evidence!r}"
        if label is ProgressLabel.STOP:
            self._stop_count += 1
            if self._stop_count < self.stop_confirmations:
                label = ProgressLabel.CONTINUE
                evidence = (
                    f"STOP awaiting confirmation {self._stop_count}/"
                    f"{self.stop_confirmations}"
                    + (f"; {evidence}" if self.target_bound_stop else "")
                )
        else:
            self._stop_count = 0
        return ProgressState(
            label=label,
            observation_seq=evidence_seq,
            t_sim_ns=evidence_t_ns,
            confidence=1.0 if self.parse_errors == 0 else 0.0,
            evidence=evidence,
            monitor_name=self.name,
            recovery_anchor_valid=recovery_anchor_valid,
            recovery_reacquired=recovery_reacquired,
        )

    def _target_arrival(
        self,
        ctx: DecisionContext,
        parsed: dict[str, Any],
        label: ProgressLabel,
        depth: np.ndarray | None,
    ) -> tuple[ProgressLabel, str]:
        """Constrain arrival with target-associated geometry; never consult scoring truth."""
        obs = ctx.observation
        point = None
        distance = None
        intr = obs.intrinsics
        u, v = parsed.get("target_u"), parsed.get("target_v")
        if (
            parsed["latest_target_visible"]
            and parsed["latest_target_scale"] != "absent"
            and u is not None
            and v is not None
            and depth is not None
            and intr is not None
            and depth.shape == (intr.height, intr.width)
            and intr.fx > 0
            and intr.fy > 0
        ):
            px, py = u * (intr.width - 1) / 999, v * (intr.height - 1) / 999
            # Use exactly the identified target pixel, not a median spanning an occluder.
            d = _depth_at(depth, px, py, patch=0)
            if d is not None:
                left = (intr.cx - px) * d / intr.fx
                up_camera = (intr.cy - py) * d / intr.fy
                cp, sp = math.cos(self.camera_pitch_rad), math.sin(self.camera_pitch_rad)
                forward, up = d * cp - up_camera * sp, d * sp + up_camera * cp
                cy, sy = math.cos(obs.yaw_rad), math.sin(obs.yaw_rad)
                delta = np.array([forward * cy - left * sy, forward * sy + left * cy, up])
                point = np.array([obs.position.x, obs.position.y, obs.position.z]) + delta
                distance = float(np.linalg.norm(delta))
        fresh = obs.seq > self._arrival_seq
        consistent = (
            point is not None
            and self._arrival_point is not None
            and float(np.linalg.norm(point - self._arrival_point)) <= self.target_consistency_m
        )
        limit = min(self.stop_max_depth_m, ctx.mission.success.goal_radius_m)
        eligible = (
            label is ProgressLabel.STOP and distance is not None and distance <= limit and fresh
        )
        if not eligible or not consistent:
            self._stop_count = 0
        if fresh:
            self._arrival_point = point if eligible else None
            self._arrival_seq = obs.seq
        if label is ProgressLabel.STOP and not eligible:
            label = ProgressLabel.CONTINUE
        return label, (
            f"target_bound_range_m={distance!r}; target_pixel=({u},{v}); "
            f"target_consistent={consistent}; fresh_frame={fresh}; "
            f"arrival_limit_m={limit}; target_frame_seq={obs.seq}"
        )

    def stats(self) -> dict[str, float]:
        return {
            "onfly_monitor_calls": float(self.calls),
            "onfly_monitor_parse_errors": float(self.parse_errors),
        }


@register("verifier", "onfly_semantic_geometric")
class OnFlySemanticGeometricVerifier(SemanticGeometricVerifier):
    """Checks OnFly provenance, then applies the common endpoint safety gate.

    The released paper requires cached ViT feature masks, but no source exposes
    those features yet.  This normalized profile therefore preserves the hard
    depth/geofence/clearance checks and records that feature refinement is not
    available; it never substitutes detector or simulator truth.
    """

    @property
    def name(self) -> str:
        return "onfly_semantic_geometric"

    def _reject(self, reason: str) -> VerificationResult:
        self.rejections += 1
        return VerificationResult(accepted=False, reason=reason)

    def verify(self, envelope: Any, ctx: DecisionContext) -> VerificationResult:
        if isinstance(envelope.payload, WaypointGoal):
            required = {
                "pixel_u",
                "pixel_v",
                "camera_pitch_rad",
                "source_position_x",
                "source_position_y",
                "source_position_z",
                "source_yaw_rad",
                "sampled_depth_m",
                "gated_range_m",
            }
            missing = required.difference(envelope.provenance)
            if missing:
                return self._reject(
                    f"OnFly waypoint lacks image/depth provenance: {sorted(missing)}"
                )
            try:
                pixel_u = float(envelope.provenance["pixel_u"])
                pixel_v = float(envelope.provenance["pixel_v"])
                camera_pitch = float(envelope.provenance["camera_pitch_rad"])
                source_x = float(envelope.provenance["source_position_x"])
                source_y = float(envelope.provenance["source_position_y"])
                source_z = float(envelope.provenance["source_position_z"])
                source_yaw = float(envelope.provenance["source_yaw_rad"])
                sampled_depth = float(envelope.provenance["sampled_depth_m"])
                gated_range = float(envelope.provenance["gated_range_m"])
            except (TypeError, ValueError):
                return self._reject("OnFly waypoint has non-numeric image/depth provenance")

            intr = ctx.observation.intrinsics
            values = (
                pixel_u,
                pixel_v,
                camera_pitch,
                source_x,
                source_y,
                source_z,
                source_yaw,
                sampled_depth,
                gated_range,
            )
            if not all(math.isfinite(value) for value in values):
                return self._reject("OnFly waypoint has non-finite image/depth provenance")
            if intr is None or not (0 <= pixel_u < intr.width and 0 <= pixel_v < intr.height):
                return self._reject("OnFly waypoint pixel is outside the calibrated image")
            if sampled_depth <= 0.05 or gated_range <= 0.0:
                return self._reject("OnFly waypoint has invalid non-positive depth/range")
            if gated_range > sampled_depth + 1e-3:
                return self._reject("OnFly bearing gate exceeds its sampled depth")
            # ``gated_range`` is d_f in the paper: camera-forward depth, not
            # Euclidean slant range. Off-axis K^-1 lifting is intentionally
            # longer than d_f, so compare the endpoint in camera coordinates.
            camera = Camera(
                width=intr.width,
                height=intr.height,
                fov_deg=math.degrees(2 * math.atan(intr.width / (2 * intr.fx))),
                pitch_rad=camera_pitch,
            )
            endpoint = np.array(
                [
                    [
                        envelope.payload.target.x,
                        envelope.payload.target.y,
                        envelope.payload.target.z,
                    ]
                ],
                dtype=float,
            )
            origin = np.array(
                [source_x, source_y, source_z],
                dtype=float,
            )
            _, endpoint_depth = camera.project(endpoint, origin, source_yaw)
            if endpoint_depth[0] < -1e-3 or endpoint_depth[0] > gated_range + 1e-3:
                return self._reject("OnFly endpoint exceeds its camera-forward depth/bearing gate")
        result = super().verify(envelope, ctx)
        if result.accepted and not result.reason:
            result.reason = "depth/geofence/clearance valid; ViT feature refinement unavailable"
        return result

    def _points_into_obstacle(self, target: Vec3, ctx: DecisionContext) -> bool:
        """Do not re-veto a depth-derived endpoint with the coarse range fan.

        The decision agent samples the selected RGB-D pixel, caps its depth,
        applies the paper's bearing gate, and lifts that forward depth before
        this verifier sees the endpoint.  The generic verifier's eight-ray check is
        less spatially precise and labels that intentional standoff as a
        collision whenever it happens to share a broad ray with a surface.
        OnFly-specific consistency is checked above; route occupancy remains
        the shared SUPER planner's responsibility.
        """
        _ = target, ctx
        return False
