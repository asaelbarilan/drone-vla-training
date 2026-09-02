"""Clean-room See, Point, Fly waypoint policy.

The implementation follows Hu et al. (CoRL 2025) from the paper equations and
supplement, not from their proprietary source. A frozen VLM emits one normalized
image point plus a discrete intended-travel label; tested geometry maps that
intermediate representation to the benchmark's shared waypoint contract.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    MissionDirective,
    MissionSpec,
    ProgressLabel,
    Vec3,
    WaypointGoal,
)
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext, InferenceRequest
from uavlab.plugins.reasoning.base import BasePolicy

SPF_PROMPT = """You are the spatial waypoint policy for a small autonomous drone.

MISSION: {instruction}

Look at the current forward camera image and choose exactly one image point for
the drone's next safe movement. Point directly at the requested goal when it is
visible. Otherwise point at visible free space that best advances the mission.

Return one JSON object and nothing else:
{{"u": <integer 0-1000>, "v": <integer 0-1000>, "distance": <integer 1-10>}}

Coordinates are normalized: (0,0) is top-left, (500,500) is the image center
and (1000,1000) is bottom-right. `distance` is intended forward travel, not
sensor depth. Use this ordered visual scale: 1 only when the requested target is
extremely close (roughly more than 35% of image width); 2 when very close
(roughly 25-35%); 3-5 at medium apparent size; and 6-10 when far/small. A tiny
target should be 9-10. When the target is not visible, choose a safe search
point and use 5. Never reverse this scale.
"""

SPF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "u": {"type": "integer", "minimum": 0, "maximum": 1000},
        "v": {"type": "integer", "minimum": 0, "maximum": 1000},
        "distance": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["u", "v", "distance"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class SPFPoint:
    """Strict model-authored image-space action."""

    u: int
    v: int
    distance: int


def adaptive_distance_m(
    label: int,
    *,
    scale_m: float = 10.0,
    levels: int = 10,
    exponent: float = 1.8,
    minimum_m: float = 0.1,
) -> float:
    """Published nonlinear travel-distance map (SPF Eq. 2)."""
    if isinstance(label, bool) or not isinstance(label, int) or not 1 <= label <= levels:
        raise ValueError(f"distance label must be an integer in [1,{levels}]")
    return max(minimum_m, scale_m * (label / levels) ** exponent)


def parse_spf_point(text: str) -> SPFPoint:
    """Parse only the declared JSON object; prose and partial outputs fail closed."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("SPF model output is not valid JSON") from exc
    if not isinstance(value, dict) or set(value) != {"u", "v", "distance"}:
        raise ValueError("SPF model output must contain exactly u, v and distance")
    values = (value["u"], value["v"], value["distance"])
    if any(isinstance(item, bool) or not isinstance(item, int) for item in values):
        raise ValueError("SPF u, v and distance must be integers")
    u, v, distance = values
    if not 0 <= u <= 1000 or not 0 <= v <= 1000 or not 1 <= distance <= 10:
        raise ValueError("SPF output is outside the declared normalized ranges")
    return SPFPoint(u=u, v=v, distance=distance)


def point_to_enu(
    point: SPFPoint,
    *,
    position: Vec3,
    yaw_rad: float,
    width: int,
    height: int,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    camera_pitch_rad: float,
    distance_m: float,
    min_altitude_m: float,
) -> Vec3:
    """SPF pinhole lift followed by camera/body to ENU transformation.

    `distance_m` is forward camera travel, not Euclidean ray length and not a
    depth-sensor sample. This preserves the paper's `S_y=d_adj` convention.
    """
    if width <= 0 or height <= 0 or fx <= 0 or fy <= 0 or distance_m <= 0:
        raise ValueError("valid intrinsics and positive travel distance are required")

    pixel_u = point.u * width / 1000.0
    pixel_v = point.v * height / 1000.0
    right_camera = (pixel_u - cx) * distance_m / fx
    up_camera = (cy - pixel_v) * distance_m / fy
    forward_camera = distance_m

    # Invert the fixed camera pitch to express the displacement in body axes.
    cos_p = math.cos(-camera_pitch_rad)
    sin_p = math.sin(-camera_pitch_rad)
    forward_body = forward_camera * cos_p + up_camera * sin_p
    up_body = -forward_camera * sin_p + up_camera * cos_p

    # ENU convention used by the shared adapter: yaw=0 faces +x and body-right
    # is -y. This is the same transform used by the tested Camera utility.
    cos_y = math.cos(yaw_rad)
    sin_y = math.sin(yaw_rad)
    east_delta = forward_body * cos_y + right_camera * sin_y
    north_delta = forward_body * sin_y - right_camera * cos_y
    return Vec3(
        x=position.x + east_delta,
        y=position.y + north_delta,
        z=max(min_altitude_m, position.z + up_body),
    )


@register("policy", "spf_waypoint")
class SPFWaypointPolicy(BasePolicy):
    """Real frozen-VLM implementation of C2's SPF waypoint authority."""

    requires_vision = True
    requires_real_inference = True

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "qwen3-vl:8b")
        super().__init__(**params)
        self.scale_m = float(params.get("scale_m", 10.0))
        self.levels = int(params.get("levels", 10))
        self.exponent = float(params.get("exponent", 1.8))
        self.minimum_step_m = float(params.get("minimum_step_m", 0.1))
        self.camera_pitch_rad = float(params.get("camera_pitch_rad", -0.15))
        self.min_altitude_m = float(params.get("min_altitude_m", 0.5))
        self.stop_label_max = int(params.get("stop_label_max", 2))
        self.stop_confirmations = int(params.get("stop_confirmations", 2))
        self.waypoint_tolerance_m = float(params.get("waypoint_tolerance_m", 0.35))
        if self.levels != 10:
            raise ValueError("the paper-locked SPF profile requires exactly 10 labels")
        if not 1 <= self.stop_label_max <= self.levels:
            raise ValueError("stop_label_max must lie inside the label scale")
        if self.stop_confirmations < 1:
            raise ValueError("stop_confirmations must be positive")
        self._near_count = 0
        self.valid_outputs = 0
        self.invalid_outputs = 0
        self.waypoints = 0
        self.stop_outputs = 0
        self._label_sum = 0
        self._label_counts = [0] * 11
        self._last_point: SPFPoint | None = None
        self._last_step_m = 0.0

    @property
    def name(self) -> str:
        return "spf_waypoint"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("waypoint", "mission_directive")

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self._near_count = 0
        self.valid_outputs = 0
        self.invalid_outputs = 0
        self.waypoints = 0
        self.stop_outputs = 0
        self._label_sum = 0
        self._label_counts = [0] * 11
        self._last_point = None
        self._last_step_m = 0.0

    async def _infer(self, ctx: DecisionContext) -> SPFPoint:
        if self.services is None or self.services.inference is None:
            raise RuntimeError("SPF requires a real inference backend")
        ref = ctx.observation.rgb
        intrinsics = ctx.observation.intrinsics
        if ref is None or intrinsics is None:
            raise RuntimeError("SPF requires synchronized RGB and camera intrinsics")

        from uavlab.core.frame_store import global_store

        image = global_store().get(ref.uri)
        if image is None:
            raise RuntimeError(f"no RGB frame stored behind {ref.uri!r}")
        backend = self.services.inference
        encode = getattr(backend, "encode_image", None)
        if not callable(encode):
            raise RuntimeError("SPF inference backend cannot encode images")
        prompt = SPF_PROMPT.format(instruction=ctx.mission.instruction)
        result = await backend.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role="policy",
                prompt_hash="spf:point-distance:v1",
                input_tokens=len(prompt) // 4,
                image_count=1,
                observation_seq=ctx.observation.seq,
                prompt=prompt,
                images=(encode(image),),
                response_schema=SPF_SCHEMA,
            )
        )
        try:
            point = parse_spf_point(str(result.payload or ""))
        except ValueError as exc:
            self.invalid_outputs += 1
            raise RuntimeError(f"invalid SPF model output: {exc}") from exc
        self.valid_outputs += 1
        self._label_sum += point.distance
        self._label_counts[point.distance] += 1
        self._last_point = point
        return point

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        point = await self._infer(ctx)
        if point.distance <= self.stop_label_max:
            self._near_count += 1
        else:
            self._near_count = 0

        provenance = {
            "spf_u": str(point.u),
            "spf_v": str(point.v),
            "spf_distance_label": str(point.distance),
            "spf_near_count": str(self._near_count),
            "implementation": "clean_room_paper_equations",
        }
        if self._near_count >= self.stop_confirmations and self.self_terminate:
            self._stopped = True
            self.stop_outputs += 1
            return self.envelope(
                ctx,
                DecisionKind.MISSION_DIRECTIVE,
                MissionDirective(
                    label=ProgressLabel.STOP,
                    rationale="repeated SPF near-travel label",
                ),
                0.8,
                note="spf repeated near label",
                extra=provenance,
            )

        intr = ctx.observation.intrinsics
        assert intr is not None
        step_m = adaptive_distance_m(
            point.distance,
            scale_m=self.scale_m,
            levels=self.levels,
            exponent=self.exponent,
            minimum_m=self.minimum_step_m,
        )
        target = point_to_enu(
            point,
            position=ctx.observation.position,
            yaw_rad=ctx.observation.yaw_rad,
            width=intr.width,
            height=intr.height,
            fx=intr.fx,
            fy=intr.fy,
            cx=intr.cx,
            cy=intr.cy,
            camera_pitch_rad=self.camera_pitch_rad,
            distance_m=step_m,
            min_altitude_m=max(self.min_altitude_m, self._min_alt),
        )
        self._last_step_m = step_m
        self.waypoints += 1
        provenance["spf_step_m"] = f"{step_m:.6f}"
        return self.envelope(
            ctx,
            DecisionKind.WAYPOINT,
            WaypointGoal(
                target=target,
                target_label=self.target_label,
                tolerance_m=min(self.waypoint_tolerance_m, max(step_m * 0.5, 0.05)),
                stop_at_target=False,
            ),
            0.65,
            note="spf point-distance waypoint",
            extra=provenance,
        )

    def stats(self) -> dict[str, float]:
        stats = {
            "spf_valid_outputs": float(self.valid_outputs),
            "spf_invalid_outputs": float(self.invalid_outputs),
            "spf_waypoints": float(self.waypoints),
            "spf_stop_outputs": float(self.stop_outputs),
            "spf_near_count": float(self._near_count),
            "spf_mean_distance_label": (
                self._label_sum / self.valid_outputs if self.valid_outputs else 0.0
            ),
            "spf_last_step_m": float(self._last_step_m),
        }
        stats.update(
            {
                f"spf_distance_label_{label}": float(self._label_counts[label])
                for label in range(1, 11)
            }
        )
        return stats
