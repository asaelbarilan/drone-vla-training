"""Real vision-language policies.

The design follows the point-and-fly family rather than asking a VLM for metric
coordinates. The model is shown the camera frame and the instruction, and it
answers with a **pixel** — where in this image should I head? The unprojection
from pixel to world waypoint is done by :meth:`Camera.unproject`, which is code
that can be unit-tested.

That split matters for the study. Asking a language model for "x=12.4, y=-8.1"
tests its ability to invent plausible numbers; asking it to point at the target
tests visual grounding, which is the thing C2 claims to be about. It also keeps
the failure modes separable: a wrong pixel is a perception failure, a wrong
waypoint from a right pixel is a geometry bug.

Everything the model returns is parsed into the same `DecisionEnvelope` the
scripted policies produce, so a real VLM and a stand-in are interchangeable and
the rest of the runtime cannot tell which is running.
"""

from __future__ import annotations

import json
import re
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

PROMPT = """You are the vision system of a small autonomous drone.

MISSION: {instruction}
The target is a RED tower. Grey shapes are obstacles. Green shapes are not the target.

The camera image is {width} by {height} pixels. Pixel (0,0) is the TOP-LEFT.

Answer with ONE line of JSON and nothing else:
{{"found": <true|false>, "u": <int 0-{umax}>, "v": <int 0-{vmax}>, "arrived": <true|false>}}

- "found": is the RED target visible in this image?
- "u","v": the pixel at the base of the RED target. Use 0,0 when found is false.
- "arrived": true only if the RED target fills much of the frame and is very close.

JSON:"""


@register("policy", "vlm_point_waypoint")
class VLMPointWaypointPolicy(BasePolicy):
    """A real VLM grounding a waypoint by pointing at the image.

    Slots into exactly the position `vlm_waypoint` occupies, so C2-C6 become
    real-model architectures by changing two lines of YAML and nothing else.
    """

    requires_vision = True
    """Declares that this policy cannot run without rendered frames.

    Read by the verification harness so a vision architecture is routed to a
    rendering environment rather than reported as broken. Declaring the need is
    better than inferring it from the plugin name."""

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "gemma3:4b")
        super().__init__(**params)
        self.hop_m = float(params.get("hop_m", 12.0))
        self.arrival_hop_m = float(params.get("arrival_hop_m", 4.0))
        self.min_altitude_m = float(params.get("min_altitude_m", 2.0))
        self.explore_when_unseen = bool(params.get("explore_when_unseen", True))

        self.parse_failures = 0
        self.not_found = 0
        self.found = 0
        self._last_raw = ""

    @property
    def name(self) -> str:
        return "vlm_point_waypoint"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("waypoint", "mission_directive")

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self.parse_failures = 0
        self.not_found = 0
        self.found = 0
        self._last_raw = ""

    # -- model call ---------------------------------------------------------

    async def _ask(self, ctx: DecisionContext) -> dict[str, Any] | None:
        """Show the frame, get a pixel back. Returns ``None`` if unusable."""
        if self.services is None or self.services.inference is None:
            return None
        ref = ctx.observation.rgb
        if ref is None:
            return None

        from uavlab.core.frame_store import global_store

        image = global_store().get(ref.uri)
        if image is None:
            # No pixels behind the reference: the environment is not rendering.
            # Fail loudly rather than quietly degrading to a blind policy that
            # would still produce plausible-looking numbers.
            raise RuntimeError(
                f"no frame behind {ref.uri!r}. A vision policy needs a rendering "
                "environment: set `render: true` in the environment params."
            )

        backend = self.services.inference
        encode = getattr(backend, "encode_image", None)
        images = (encode(image),) if callable(encode) else ()

        intr = ctx.observation.intrinsics
        width = intr.width if intr else image.width
        height = intr.height if intr else image.height
        prompt = PROMPT.format(
            instruction=ctx.mission.instruction,
            width=width,
            height=height,
            umax=width - 1,
            vmax=height - 1,
        )

        result = await backend.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role="policy",
                prompt_hash=f"{self.name}:v1",
                input_tokens=len(prompt) // 4,
                image_count=len(images),
                observation_seq=ctx.observation.seq,
                prompt=prompt,
                images=images,
            )
        )
        self._last_raw = str(result.payload or "")
        return self._parse(self._last_raw)

    def _parse(self, text: str) -> dict[str, Any] | None:
        """Pull the first JSON object out of the reply.

        Small models wrap JSON in prose or code fences often enough that strict
        parsing would turn a formatting quirk into a navigation failure. Parse
        failures are counted, not hidden — a policy whose model cannot answer in
        the requested format is a real result about that model.
        """
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match is None:
            self.parse_failures += 1
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            self.parse_failures += 1
            return None
        if not isinstance(data, dict):
            self.parse_failures += 1
            return None
        return data

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes", "1")
        return bool(value)

    # -- policy -------------------------------------------------------------

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        answer = await self._ask(ctx)

        if answer is None or not self._as_bool(answer.get("found", False)):
            self.not_found += 1
            if not self.explore_when_unseen:
                return None
            return self.envelope(
                ctx,
                DecisionKind.WAYPOINT,
                WaypointGoal(target=self.explore_target(ctx), tolerance_m=2.5),
                0.1,
                note="vlm: target not visible; searching",
            )

        self.found += 1
        arrived = self._as_bool(answer.get("arrived", False))
        if arrived and self.self_terminate:
            self._stopped = True
            return self.envelope(
                ctx,
                DecisionKind.MISSION_DIRECTIVE,
                MissionDirective(label=ProgressLabel.STOP, rationale="vlm reports arrival"),
                0.7,
            )

        target = self._pixel_to_waypoint(answer, ctx, arrived)
        if target is None:
            self.parse_failures += 1
            return self.envelope(
                ctx,
                DecisionKind.WAYPOINT,
                WaypointGoal(target=self.explore_target(ctx), tolerance_m=2.5),
                0.1,
                note="vlm: unusable pixel; searching",
            )

        return self.envelope(
            ctx,
            DecisionKind.WAYPOINT,
            WaypointGoal(
                target=target,
                target_label=self.target_label,
                tolerance_m=1.5,
                stop_at_target=False,
            ),
            0.6,
            note="vlm: pointed",
        )

    def _pixel_to_waypoint(
        self, answer: dict[str, Any], ctx: DecisionContext, arrived: bool
    ) -> Vec3 | None:
        import numpy as np

        from uavlab.adapters.gym.render import Camera

        intr = ctx.observation.intrinsics
        if intr is None:
            return None
        try:
            u = float(answer.get("u", 0))
            v = float(answer.get("v", 0))
        except (TypeError, ValueError):
            return None
        if not (0.0 <= u <= intr.width and 0.0 <= v <= intr.height):
            return None

        # Rebuilt from the *contract*, not from the environment, so this policy
        # works against any adapter that reports intrinsics.
        camera = Camera(
            width=intr.width,
            height=intr.height,
            fov_deg=self._fov_from(intr),
            pitch_rad=float(self.__dict__.get("camera_pitch_rad", -0.15)),
        )
        position = np.array(
            [ctx.observation.position.x, ctx.observation.position.y, ctx.observation.position.z]
        )
        hop = self.arrival_hop_m if arrived else self.hop_m
        point = camera.unproject(u, v, hop, position, ctx.observation.yaw_rad)

        # The model points at the *base* of the tower, which is on the ground.
        # Flying to it literally would descend into terrain, so hold altitude.
        return Vec3(
            x=float(point[0]),
            y=float(point[1]),
            z=max(self.min_altitude_m, float(ctx.observation.position.z)),
        )

    @staticmethod
    def _fov_from(intr: Any) -> float:
        import math

        return math.degrees(2.0 * math.atan((intr.width / 2.0) / intr.fx))

    def stats(self) -> dict[str, float]:
        total = self.found + self.not_found
        return {
            "vlm_found": float(self.found),
            "vlm_not_found": float(self.not_found),
            "vlm_parse_failures": float(self.parse_failures),
            "vlm_found_rate": (self.found / total) if total else 0.0,
        }
