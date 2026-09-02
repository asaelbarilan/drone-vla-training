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
from uavlab.plugins.memory.stores import DECISION_KIND
from uavlab.plugins.reasoning.base import BasePolicy, recall_target

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

ARRIVAL_CONFIRM_PROMPT = """You are the terminal safety verifier of a small drone.

This is a zoomed crop around a proposed target pixel. The mission target is a
RED tower; grey objects are obstacles and green objects are distractors.

Answer with ONE line of JSON and nothing else:
{{"confirmed": <true|false>}}

Set confirmed=true only when the RED target itself is clearly visible and close
in this crop. If the crop is grey, ambiguous, or lacks the red target, answer false.

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
        self.memory_trust_s = float(params.get("memory_trust_s", 6.0))
        """How long a remembered sighting is worth steering on.

        Without a bound the policy latches. Measured on the first version of the
        recall fallback: it flew 17 m and 9.5 m in a 60 s episode against 115 m
        and 113 m with memory disabled, because once it had *any* remembered
        target it steered at that point forever and never searched again. Ending
        20-29 m short having barely moved is worse than searching badly.

        A sighting is evidence with a shelf life. After this long unconfirmed,
        the model has looked and not seen it, and exploring is the better bet.
        """
        self.arrival_hop_m = float(params.get("arrival_hop_m", 4.0))
        self.min_altitude_m = float(params.get("min_altitude_m", 2.0))
        self.range_mode = str(params.get("range_mode", "fixed_hop"))
        self.range_min_baseline_m = float(params.get("range_min_baseline_m", 1.0))
        self.range_min_parallax_deg = float(params.get("range_min_parallax_deg", 1.5))
        self.range_max_ray_gap_m = float(params.get("range_max_ray_gap_m", 2.5))
        self.range_max_m = float(params.get("range_max_m", 90.0))
        self.range_history_s = float(params.get("range_history_s", 20.0))
        self.range_history_size = int(params.get("range_history_size", 8))
        self.depth_patch_px = int(params.get("depth_patch_px", 3))
        self.range_track_tolerance_m = float(params.get("range_track_tolerance_m", 2.5))
        self.range_stop_m = float(params.get("range_stop_m", 2.0))
        self.range_stop_confirmations = int(params.get("range_stop_confirmations", 2))
        self.range_semantic_confirmation = bool(
            params.get("range_semantic_confirmation", False)
        )
        self.range_confirm_crop_px = int(params.get("range_confirm_crop_px", 48))
        self.range_probe_m = float(params.get("range_probe_m", 0.0))
        self.trust_model_arrival = bool(params.get("trust_model_arrival", True))
        self.memory_trust_s = float(params.get("memory_trust_s", 6.0))
        """How long a remembered sighting keeps steering the vehicle.

        Without a bound the policy latches. Measured on the first version of the
        recall fallback: once it had any memory it stopped searching entirely and
        flew 9-17 m in a 60 s episode, against 113-115 m with no memory at all.
        It was orbiting a position the model could no longer confirm.

        A remembered target is a hypothesis, and an unconfirmed hypothesis has to
        expire or it becomes a belief. After this many seconds without the model
        seeing the target again, exploration resumes.
        """
        self.explore_when_unseen = bool(params.get("explore_when_unseen", True))

        self.parse_failures = 0
        self.not_found = 0
        self.found = 0
        self.arrived_reports = 0
        self.range_estimates = 0
        self.range_rejections = 0
        self.range_arrivals = 0
        self.range_probes = 0
        self.range_confirmation_calls = 0
        self.range_confirmation_rejections = 0
        self._range_near_count = 0
        self._last_range_m = 0.0
        self._range_stop_ready = False
        self._last_range_source = "fixed_hop"
        self._bearing_history: list[tuple[int, Any, Any]] = []
        self._range_probe_target: Vec3 | None = None
        self._depth_frames: dict[int, Any] = {}
        self._rgb_frames: dict[int, Any] = {}
        self._last_pixel: tuple[float, float] | None = None
        self._range_target_history: list[tuple[int, Any]] = []
        self._range_consistent_count = 0
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
        self.arrived_reports = 0
        self.range_estimates = 0
        self.range_rejections = 0
        self.range_arrivals = 0
        self.range_probes = 0
        self.range_confirmation_calls = 0
        self.range_confirmation_rejections = 0
        self._range_near_count = 0
        self._last_range_m = 0.0
        self._range_stop_ready = False
        self._last_range_source = "fixed_hop"
        self._bearing_history = []
        self._range_probe_target = None
        self._depth_frames = {}
        self._rgb_frames = {}
        self._last_pixel = None
        self._range_target_history = []
        self._range_consistent_count = 0
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
        self._rgb_frames[ctx.observation.seq] = image.copy()
        for old_seq in sorted(self._rgb_frames)[:-4]:
            self._rgb_frames.pop(old_seq, None)

        # Snapshot synchronized depth before awaiting slow inference. The
        # bounded frame store may evict this observation while Gemma is
        # thinking, but the returned pixel must be paired with the depth frame
        # captured at exactly the same pose and sequence.
        depth_ref = ctx.observation.depth
        if depth_ref is not None and depth_ref.shape is not None:
            depth_image = global_store().get(depth_ref.uri)
            if depth_image is not None:
                import numpy as np

                self._depth_frames[ctx.observation.seq] = np.asarray(
                    depth_image, dtype=np.float32
                ).copy()
                for old_seq in sorted(self._depth_frames)[:-4]:
                    self._depth_frames.pop(old_seq, None)

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

    async def _confirm_terminal_target(self, ctx: DecisionContext) -> bool:
        """Second semantic look at a close depth candidate.

        A depth camera can say "surface at 1.5 m" but cannot say that surface is
        the mission target. The cropped confirmation keeps termination semantic
        without introducing a renderer-specific colour rule.
        """
        if self.services is None or self.services.inference is None:
            return False
        image = self._rgb_frames.get(ctx.observation.seq)
        if image is None or self._last_pixel is None:
            return False
        u, v = self._last_pixel
        radius = max(8, self.range_confirm_crop_px)
        left = max(0, int(round(u)) - radius)
        top = max(0, int(round(v)) - radius)
        right = min(image.width, int(round(u)) + radius + 1)
        bottom = min(image.height, int(round(v)) + radius + 1)
        if right <= left or bottom <= top:
            return False
        crop = image.crop((left, top, right, bottom)).resize((224, 224))
        backend = self.services.inference
        encode = getattr(backend, "encode_image", None)
        images = (encode(crop),) if callable(encode) else ()
        self.range_confirmation_calls += 1
        result = await backend.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role="policy",
                prompt_hash=f"{self.name}:arrival-confirm:v1",
                input_tokens=len(ARRIVAL_CONFIRM_PROMPT) // 4,
                image_count=len(images),
                observation_seq=ctx.observation.seq,
                prompt=ARRIVAL_CONFIRM_PROMPT,
                images=images,
            )
        )
        answer = self._parse(str(result.payload or ""))
        confirmed = bool(answer and self._as_bool(answer.get("confirmed", False)))
        if not confirmed:
            self.range_confirmation_rejections += 1
        return confirmed

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

    def _hop_toward(self, origin: Vec3, target: Vec3) -> Vec3:
        """Cap a remembered target to the same hop the model's own waypoints use.

        A remembered position can be tens of metres away, and committing to it
        outright would fly past everything the model might see on the way. The
        cap keeps recall on the same receding-horizon footing as a live sighting.
        """
        import math

        dx, dy, dz = target.x - origin.x, target.y - origin.y, target.z - origin.z
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if distance <= self.hop_m or distance < 1e-9:
            return Vec3(x=target.x, y=target.y, z=max(self.min_altitude_m, target.z))
        scale = self.hop_m / distance
        return Vec3(
            x=origin.x + dx * scale,
            y=origin.y + dy * scale,
            z=max(self.min_altitude_m, origin.z + dz * scale),
        )

    def _remembered_target(self, ctx: DecisionContext) -> Vec3 | None:
        """Where this policy last concluded the target was.

        Consulted only when the model reports it cannot see the target. Without
        this the policy forgets a sighting the instant it leaves the frame, and
        the memory and supervision plugins configured above it have nowhere to
        land: measured, replacing C5G's keyframe memory with no memory at all
        changed the trajectory on 0 of 8 seeds, while the same removal on the
        scripted C5 changed 3 of 10.

        Two restrictions keep the configuration honest:

        * ``kinds={"decision"}`` — recall only sightings this policy committed
          to itself. Everything else in the store came from the simulated
          detector, and a Gemma configuration that reads the detector through
          memory is no longer measuring a real model as the perceiver.
        * the reasoner's directive outranks memory, which is the whole
          justification for paying for a second, slower semantic loop.
        """
        directive = ctx.last_directive
        if self.follow_directives and directive is not None and directive.target_hint is not None:
            return directive.target_hint
        if not self.use_memory:
            return None
        remembered = recall_target(ctx, self.target_label, kinds=frozenset({DECISION_KIND}))
        if remembered is None:
            return None
        age_s = (ctx.t_sim_ns - remembered.t_sim_ns) / 1e9
        if age_s > self.memory_trust_s:
            return None
        return remembered.position

    def _search_or_recall(
        self, ctx: DecisionContext, note: str
    ) -> DecisionEnvelope:
        """Head for a remembered target if there is one, otherwise search."""
        remembered = self._remembered_target(ctx)
        if remembered is None:
            return self.envelope(
                ctx,
                DecisionKind.WAYPOINT,
                WaypointGoal(target=self.explore_target(ctx), tolerance_m=2.5),
                0.1,
                note=f"{note}; searching",
            )
        return self.envelope(
            ctx,
            DecisionKind.WAYPOINT,
            WaypointGoal(
                target=self._hop_toward(ctx.observation.position, remembered),
                target_label=self.target_label,
                tolerance_m=1.5,
                stop_at_target=False,
            ),
            # Remembered evidence is worth less than a live sighting, and saying
            # so keeps "confident because I once saw it" out of the stop decision.
            0.4,
            note=f"{note}; steering on remembered target",
            extra={"from_memory": "true"},
        )

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        answer = await self._ask(ctx)

        if answer is None or not self._as_bool(answer.get("found", False)):
            self.not_found += 1
            if not self.explore_when_unseen:
                return None
            return self._search_or_recall(ctx, "vlm: target not visible")

        self.found += 1
        arrived = self._as_bool(answer.get("arrived", False))
        if arrived:
            self.arrived_reports += 1
        if arrived and self.trust_model_arrival and self.self_terminate:
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
            return self._search_or_recall(ctx, "vlm: unusable pixel")

        if self._range_stop_ready and self.range_semantic_confirmation:
            if not await self._confirm_terminal_target(ctx):
                self._range_stop_ready = False
                self._range_near_count = 0

        if self._range_stop_ready and self.self_terminate:
            self._stopped = True
            self.range_arrivals += 1
            return self.envelope(
                ctx,
                DecisionKind.MISSION_DIRECTIVE,
                MissionDirective(
                    label=ProgressLabel.STOP,
                    rationale=(
                        f"{self._last_range_source.replace('_', '-')} range "
                        f"{self._last_range_m:.2f} m "
                        f"confirmed {self._range_near_count} times"
                    ),
                ),
                0.8,
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
            note=(
                f"vlm: pointed; {self._last_range_source}"
                + (
                    f"={self._last_range_m:.2f}m"
                    if self._last_range_source in ("two_view", "depth")
                    else ""
                )
            ),
            extra={"range_source": self._last_range_source},
        )

    def _two_view_target(
        self, t_sim_ns: int, origin: Any, direction: Any
    ) -> Any | None:
        """Triangulate the current pixel against earlier grounded pixels.

        Only odometry, calibrated intrinsics and VLM pixels enter this method.
        The simulator's semantic detections and goal coordinates are outside the
        policy contract and cannot be reached here.
        """
        import math

        import numpy as np

        from uavlab.core.camera import triangulate_rays

        oldest_ns = t_sim_ns - int(self.range_history_s * 1e9)
        self._bearing_history = [
            item for item in self._bearing_history if item[0] >= oldest_ns
        ]

        best: tuple[float, Any, float] | None = None
        for _, previous_origin, previous_direction in self._bearing_history:
            baseline = float(np.linalg.norm(origin - previous_origin))
            if baseline < self.range_min_baseline_m:
                continue
            cosine = float(np.clip(np.dot(previous_direction, direction), -1.0, 1.0))
            parallax_deg = math.degrees(math.acos(cosine))
            if parallax_deg < self.range_min_parallax_deg:
                continue
            result = triangulate_rays(
                previous_origin, previous_direction, origin, direction
            )
            if result is None:
                continue
            midpoint, gap_m, previous_range_m, current_range_m = result
            if gap_m > self.range_max_ray_gap_m:
                continue
            if not (
                0.25 <= previous_range_m <= self.range_max_m
                and 0.25 <= current_range_m <= self.range_max_m
            ):
                continue
            # Prefer wider parallax and tighter ray agreement.
            score = parallax_deg / (1.0 + gap_m)
            if best is None or score > best[0]:
                best = (score, midpoint, float(np.linalg.norm(midpoint - origin)))

        self._bearing_history.append((t_sim_ns, origin.copy(), direction.copy()))
        self._bearing_history = self._bearing_history[-max(2, self.range_history_size) :]

        if best is None:
            self.range_rejections += 1
            return None
        _, target, range_m = best
        self.range_estimates += 1
        self._last_range_m = range_m
        return target

    def _depth_target(
        self, ctx: DecisionContext, u: float, v: float, camera: Any, position: Any
    ) -> Any | None:
        """Metric target point from the depth camera at the VLM-grounded pixel."""
        import numpy as np

        from uavlab.core.frame_store import global_store

        ref = ctx.observation.depth
        if ref is None or ref.shape is None:
            self.range_rejections += 1
            return None
        depth_image = self._depth_frames.get(ctx.observation.seq)
        if depth_image is None:
            depth_image = global_store().get(ref.uri)
        if depth_image is None:
            self.range_rejections += 1
            return None
        depth = np.asarray(depth_image, dtype=float)
        if depth.ndim != 2:
            self.range_rejections += 1
            return None
        radius = max(0, self.depth_patch_px)
        ui, vi = int(round(u)), int(round(v))
        x0, x1 = max(0, ui - radius), min(depth.shape[1], ui + radius + 1)
        y0, y1 = max(0, vi - radius), min(depth.shape[0], vi + radius + 1)
        patch = depth[y0:y1, x0:x1]
        valid = patch[np.isfinite(patch) & (patch > 0.2) & (patch <= self.range_max_m)]
        if valid.size == 0:
            self.range_rejections += 1
            return None
        camera_depth_m = float(np.median(valid))
        target = camera.unproject(u, v, camera_depth_m, position, ctx.observation.yaw_rad)
        self._last_range_m = float(np.linalg.norm(target - position))
        oldest_ns = ctx.t_sim_ns - int(self.range_history_s * 1e9)
        self._range_target_history = [
            item for item in self._range_target_history if item[0] >= oldest_ns
        ]
        matches = sum(
            float(np.linalg.norm(previous - target)) <= self.range_track_tolerance_m
            for _, previous in self._range_target_history
        )
        self._range_consistent_count = 1 + matches
        self._range_target_history.append((ctx.t_sim_ns, target.copy()))
        self._range_target_history = self._range_target_history[-max(2, self.range_history_size) :]
        self.range_estimates += 1
        return target

    def _pixel_to_waypoint(
        self, answer: dict[str, Any], ctx: DecisionContext, arrived: bool
    ) -> Vec3 | None:
        import numpy as np

        from uavlab.core.camera import Camera

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
        self._last_pixel = (u, v)

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
        self._range_stop_ready = False
        self._last_range_source = "fixed_hop"
        point = None
        if self.range_mode == "depth":
            estimate = self._depth_target(ctx, u, v, camera, position)
            if estimate is not None:
                self._last_range_source = "depth"
                if self._last_range_m <= self.range_stop_m:
                    # A slow VLM may cross the whole terminal radius between two
                    # calls. Confirm against an earlier estimate of the same
                    # stationary world point, rather than requiring two near
                    # frames that cannot physically occur at this call rate.
                    self._range_near_count = self._range_consistent_count
                else:
                    self._range_near_count = 0
                self._range_stop_ready = (
                    self._range_near_count >= max(1, self.range_stop_confirmations)
                )
        elif self.range_mode == "two_view":
            direction = camera.ray_world(u, v, ctx.observation.yaw_rad)
            estimate = self._two_view_target(ctx.t_sim_ns, position, direction)
            if estimate is not None:
                self._range_probe_target = None
                self._last_range_source = "two_view"
                if self._last_range_m <= self.range_stop_m:
                    self._range_near_count += 1
                else:
                    self._range_near_count = 0
                self._range_stop_ready = (
                    self._range_near_count >= max(1, self.range_stop_confirmations)
                )
            elif self.range_probe_m > 0.0:
                if self._range_probe_target is None:
                    # A bounded lateral move creates parallax when normal flight
                    # is directly along the target bearing. It is a waypoint
                    # through the ordinary planner, not a raw motion command.
                    side = np.array([-direction[1], direction[0], 0.0], dtype=float)
                    side_norm = float(np.linalg.norm(side))
                    if side_norm > 1e-6:
                        side /= side_norm
                        probe = position + self.range_probe_m * side
                        self._range_probe_target = Vec3(
                            x=float(probe[0]),
                            y=float(probe[1]),
                            z=max(self.min_altitude_m, float(position[2])),
                        )
                        self.range_probes += 1
                if self._range_probe_target is not None:
                    remaining = ctx.observation.position.distance_to(
                        self._range_probe_target
                    )
                    if remaining > 0.5:
                        point = np.array(
                            [
                                self._range_probe_target.x,
                                self._range_probe_target.y,
                                self._range_probe_target.z,
                            ],
                            dtype=float,
                        )
                        self._last_range_source = "active_probe"
        # Range is deliberately an arrival sensor, not a steering target. Pixel
        # noise and same-label mistakes can put valid depth on the wrong surface;
        # allowing that point to change control was tested and rejected.
        if point is None:
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
            "vlm_arrived_reports": float(self.arrived_reports),
            "vlm_range_estimates": float(self.range_estimates),
            "vlm_range_rejections": float(self.range_rejections),
            "vlm_range_arrivals": float(self.range_arrivals),
            "vlm_range_probes": float(self.range_probes),
            "vlm_range_confirmation_calls": float(self.range_confirmation_calls),
            "vlm_range_confirmation_rejections": float(
                self.range_confirmation_rejections
            ),
            "vlm_range_last_m": float(self._last_range_m),
            "vlm_range_consistent_count": float(self._range_consistent_count),
        }
