"""AeroVLA's direct dual-view numerical-action policy.

Clean-room testbed adapter based on the paper and Apache-2.0 official release.
The policy owns semantic and kinematic authority: it emits one typed action or
LAND. It never asks a waypoint planner, detector, depth stop, memory, or
simulator truth for help.
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    KinematicAction,
    MissionDirective,
    MissionSpec,
    ProgressLabel,
    Vec3,
    s_to_ns,
)
from uavlab.core.frame_store import global_store
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext, InferenceRequest
from uavlab.plugins.reasoning.base import BasePolicy

NUM_BINS = 99
FORWARD_RANGE = (0.0, 5.0)
VERTICAL_DOWN_RANGE = (-5.0, 5.0)
# Executable official source uses this despite the paper text saying [-pi, pi].
YAW_RANGE = (-1.1, 1.1)


class AeroVLAOutputError(RuntimeError):
    """The model failed the strict numerical-action contract."""


@dataclass(frozen=True, slots=True)
class AeroVLAOutput:
    forward_bin: int
    vertical_bin: int
    yaw_bin: int
    land: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("forward_bin", self.forward_bin),
            ("vertical_bin", self.vertical_bin),
            ("yaw_bin", self.yaw_bin),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < NUM_BINS:
                raise AeroVLAOutputError(f"{name} must be an integer in [0, 98], got {value!r}")


def dequantize(bin_value: int, value_range: tuple[float, float]) -> float:
    if (
        isinstance(bin_value, bool)
        or not isinstance(bin_value, int)
        or not 0 <= bin_value < NUM_BINS
    ):
        raise AeroVLAOutputError(f"action bin must be an integer in [0, 98], got {bin_value!r}")
    low, high = value_range
    return (bin_value / (NUM_BINS - 1)) * (high - low) + low


def parse_aerovla_output(payload: object) -> AeroVLAOutput:
    """Parse constrained JSON or the official ``NN NN NN [LAND]`` text."""
    if not isinstance(payload, str) or not payload.strip():
        raise AeroVLAOutputError("AeroVLA backend returned no text")
    text = payload.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        expected = {"forward_bin", "vertical_bin", "yaw_bin", "land"}
        if set(value) != expected:
            raise AeroVLAOutputError(
                f"AeroVLA JSON keys must be exactly {sorted(expected)}, got {sorted(value)}"
            )
        land = value["land"]
        if not isinstance(land, bool):
            raise AeroVLAOutputError("AeroVLA JSON field 'land' must be boolean")
        return AeroVLAOutput(
            forward_bin=value["forward_bin"],
            vertical_bin=value["vertical_bin"],
            yaw_bin=value["yaw_bin"],
            land=land,
        )

    action_part = text.rsplit("Action:", 1)[-1]
    land = bool(re.search(r"(?:^|\s)<?LAND>?(?:\s|$)", action_part, flags=re.IGNORECASE))
    without_land = re.sub(r"<?LAND>?", " ", action_part, flags=re.IGNORECASE)
    tokens = re.findall(r"(?<!\d)\d{1,2}(?!\d)", without_land)
    if len(tokens) != 3:
        raise AeroVLAOutputError(
            f"official AeroVLA action must contain exactly three integer tokens; got {tokens}"
        )
    return AeroVLAOutput(*(int(token) for token in tokens), land=land)


def make_dual_view_mosaic(front: Any, down: Any, size: int = 224):
    """Front on top, down on bottom, then resize exactly once to model size."""
    from PIL import Image

    front = front.convert("RGB").resize((size, size), resample=Image.Resampling.BICUBIC)
    down = down.convert("RGB").resize((size, size), resample=Image.Resampling.BICUBIC)
    stacked = Image.new("RGB", (size, size * 2))
    stacked.paste(front, (0, 0))
    stacked.paste(down, (0, size))
    return stacked.resize((size, size), resample=Image.Resampling.BICUBIC)


def aerovla_prompt(instruction: str, hint: str, output_format: str = "json") -> str:
    """Build the shared train/inference prompt for the AeroVLA action contract."""
    if output_format == "official_text":
        return f"<image>\nFly {hint} and find the target. {instruction}\nAction: "
    if output_format != "json":
        raise ValueError("AeroVLA output_format must be json or official_text")
    return (
        "You are AeroVLA, the direct flight policy. The image is a vertical mosaic: "
        "front camera on top and downward camera on bottom. "
        f"The target is {hint}. Mission: {instruction}. "
        "Return only the required JSON. Each action bin is an integer from 0 through 98. "
        "The released AeroVLA codec is: forward_bin 0 means 0 m and 98 means 5 m; "
        "vertical_bin 0 means climb 5 m, 49 means stay level, and 98 means descend 5 m; "
        "yaw_bin 0 means turn left 1.1 rad, 49 means keep heading, and 98 means turn "
        "right 1.1 rad. Use 49—not 0—for a neutral vertical or yaw command. "
        "Choose a new action from this image and direction; do not repeat a fixed example. "
        "When the target direction is left choose yaw_bin below 49, and when it is right "
        "choose yaw_bin above 49. If the front view is blocked, reduce forward_bin and "
        "turn toward visible free space or climb; never keep commanding forward into the "
        "same obstacle. Use land=true only when the red requested target is visually "
        "aligned near the center of the downward half and the drone should terminate."
    )


def action_from_output(
    output: AeroVLAOutput,
    yaw_rad: float,
    *,
    cruise_mps: float = 1.0,
    min_duration_s: float = 0.1,
    max_yaw_rate_rps: float = 1.1,
) -> tuple[KinematicAction | None, dict[str, float]]:
    """Decode body-relative offsets to one planner-free ENU action."""
    forward = dequantize(output.forward_bin, FORWARD_RANGE)
    down = dequantize(output.vertical_bin, VERTICAL_DOWN_RANGE)
    yaw_delta_ned = dequantize(output.yaw_bin, YAW_RANGE)
    landed_by_zero = forward < 0.01 and abs(down) < 0.01 and abs(yaw_delta_ned) < 0.01
    decoded = {"forward_m": forward, "down_m": down, "yaw_delta_rad": yaw_delta_ned}
    if output.land or landed_by_zero:
        return None, decoded

    # AeroVLA/AirSim uses NED yaw (clockwise-positive); the testbed is ENU
    # (counter-clockwise-positive). Negation is the required frame transform.
    yaw_delta_enu = -yaw_delta_ned
    target_yaw = yaw_rad + yaw_delta_enu
    dx = forward * math.cos(target_yaw)
    dy = forward * math.sin(target_yaw)
    dz = -down  # official action uses NED/down-positive; testbed is ENU/up-positive.
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    translation_s = distance / max(cruise_mps, 1e-6)
    rotation_s = abs(yaw_delta_enu) / max(max_yaw_rate_rps, 1e-6)
    duration_s = max(min_duration_s, translation_s, rotation_s)
    velocity = Vec3(x=dx / duration_s, y=dy / duration_s, z=dz / duration_s)
    return (
        KinematicAction(
            velocity=velocity,
            yaw_rate_rps=yaw_delta_enu / duration_s,
            duration_s=duration_s,
        ),
        decoded,
    )


def _encode_png(image: Any) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@register("policy", "aerovla")
class AeroVLAPolicy(BasePolicy):
    """Reactive dual-view model -> numerical bins -> direct kinematic action."""

    requires_vision = True

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "gemma3:4b")
        params.setdefault("use_memory", False)
        params.setdefault("follow_directives", False)
        super().__init__(**params)
        self.output_format = str(params.get("output_format", "json"))
        if self.output_format not in {"json", "official_text"}:
            raise ValueError("AeroVLA output_format must be json or official_text")
        self.image_size = int(params.get("image_size", 224))
        self.cruise_mps = float(params.get("cruise_mps", 1.0))
        self.max_yaw_rate_rps = float(params.get("max_yaw_rate_rps", 1.1))
        self._action_until_ns = 0
        self.model_calls = 0
        self.model_land_outputs = 0
        self.parse_errors = 0

    @property
    def name(self) -> str:
        return "aerovla"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("kinematic_action", "mission_directive")

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self._action_until_ns = 0
        self.model_calls = 0
        self.model_land_outputs = 0
        self.parse_errors = 0

    def _mosaic(self, ctx: DecisionContext):
        front_ref = ctx.observation.rgb
        down_ref = ctx.observation.rgb_down
        if front_ref is None or down_ref is None:
            raise RuntimeError("AeroVLA requires synchronized front and downward RGB references")
        front = global_store().get(front_ref.uri)
        down = global_store().get(down_ref.uri)
        if front is None or down is None:
            raise RuntimeError(
                "AeroVLA image reference is unresolved; enable render and render_down "
                "in the environment"
            )
        return make_dual_view_mosaic(front, down, self.image_size)

    def _prompt(self, ctx: DecisionContext) -> str:
        hint = ctx.observation.coarse_goal_direction
        if hint is None:
            raise RuntimeError(
                "AeroVLA requires a declared coarse goal-direction prior; it is "
                "intentionally absent "
                "from unknown-location search tasks"
            )
        return aerovla_prompt(ctx.mission.instruction, hint, self.output_format)

    @staticmethod
    def _schema() -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "forward_bin": {"type": "integer", "minimum": 0, "maximum": 98},
                "vertical_bin": {"type": "integer", "minimum": 0, "maximum": 98},
                "yaw_bin": {"type": "integer", "minimum": 0, "maximum": 98},
                "land": {"type": "boolean"},
            },
            "required": ["forward_bin", "vertical_bin", "yaw_bin", "land"],
            "additionalProperties": False,
        }

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        if ctx.t_sim_ns < self._action_until_ns:
            return None
        if self.services is None or self.services.inference is None:
            raise RuntimeError("AeroVLA requires a real inference backend")

        mosaic = self._mosaic(ctx)
        prompt = self._prompt(ctx)
        result = await self.services.inference.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role="policy",
                prompt_hash=f"aerovla:{self.output_format}:v1",
                input_tokens=64,
                image_count=1,
                observation_seq=ctx.observation.seq,
                prompt=prompt,
                images=(_encode_png(mosaic),),
                response_schema=self._schema() if self.output_format == "json" else None,
            )
        )
        self.model_calls += 1
        try:
            output = parse_aerovla_output(result.payload)
        except AeroVLAOutputError:
            self.parse_errors += 1
            raise

        action, decoded = action_from_output(
            output,
            ctx.observation.yaw_rad,
            cruise_mps=self.cruise_mps,
            max_yaw_rate_rps=self.max_yaw_rate_rps,
        )
        extra = {
            "forward_bin": str(output.forward_bin),
            "vertical_bin": str(output.vertical_bin),
            "yaw_bin": str(output.yaw_bin),
            "land": str(output.land).lower(),
            "forward_m": f"{decoded['forward_m']:.6f}",
            "down_m": f"{decoded['down_m']:.6f}",
            "yaw_delta_rad": f"{decoded['yaw_delta_rad']:.6f}",
            "coarse_goal_direction": str(ctx.observation.coarse_goal_direction),
            "paper_yaw_range_discrepancy": "release[-1.1,1.1];paper[-pi,pi]",
        }
        if action is None:
            self.model_land_outputs += 1
            self._stopped = True
            return self.envelope(
                ctx,
                DecisionKind.MISSION_DIRECTIVE,
                MissionDirective(
                    label=ProgressLabel.STOP,
                    rationale="AeroVLA intrinsic LAND/near-zero action",
                ),
                1.0,
                note="model-authored intrinsic stop",
                extra=extra,
            )

        now_ns = self.services.clock.now_ns()
        self._action_until_ns = now_ns + s_to_ns(action.duration_s)
        return self.envelope(
            ctx,
            DecisionKind.KINEMATIC_ACTION,
            action,
            1.0,
            note="dual-view numerical-token direct action",
            extra=extra,
        )

    def stats(self) -> dict[str, float]:
        return {
            "aerovla_model_calls": float(self.model_calls),
            "aerovla_land_outputs": float(self.model_land_outputs),
            "aerovla_parse_errors": float(self.parse_errors),
        }
