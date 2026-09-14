"""Opt-in D-108 hover validator using VLM RGB-D identity and live odometry only."""

import math

import numpy as np

from uavlab.contracts import ProgressLabel
from uavlab.core.camera import Camera
from uavlab.core.frame_store import global_store
from uavlab.core.registry import register
from uavlab.plugins.reasoning.onfly import OnFlyMonitor, _depth_at, _encode_png


@register("monitor", "onfly_hover_monitor")
class OnFlyHoverMonitor(OnFlyMonitor):
    def __init__(self, **params):
        super().__init__(**params)
        self.stable_hover_reference = bool(params.get("stable_hover_reference", False))

    def reset(self, mission, seed):
        super().reset(mission, seed)
        if "Hold for 2 continuous seconds" not in mission.instruction:
            raise ValueError("hover monitor requires the explicit D-108 hover contract")
        self._approach = None
        self._initial_position = None
        self._hover_s = 0.0
        self._hover_last_ns = None
        self._hover_point = None
        self._reference_image = None
        self._reference_seq = None
        self._latest_hover_obs = None
        self._previous_hover_good = False

    def _hover_geometry(self, obs):
        if self._approach is None or self._tracked_target is None:
            return False
        if self._tracked_confirmations < self.stop_confirmations:
            return False
        age = (obs.t_sim_ns - self._tracked_target_t_ns) / 1e9
        if not 0 <= age <= self.arrival_memory_s:
            return False
        origin = np.array([obs.position.x, obs.position.y, obs.position.z])
        delta = self._tracked_target - origin
        along = float(delta @ self._approach)
        sideways = delta - along * self._approach
        if self.stable_hover_reference and self._initial_position is not None:
            # The approach line belongs to the initial odometry frame; selecting
            # another visible body pixel must not move that line underneath us.
            start = self._initial_position
            displacement = origin - np.array([start.x, start.y, start.z])
            sideways = displacement - (displacement @ self._approach) * self._approach
        vertical = (
            obs.position.z - self._initial_position.z if self._initial_position else float("inf")
        )
        cross = float(math.hypot(np.linalg.norm(sideways[:2]), vertical))
        if not (
            0.75 <= np.linalg.norm(delta) <= 1.25
            and along > 0
            and cross <= 0.35
            and obs.velocity.norm() <= 0.2
        ):
            return False
        intr = obs.intrinsics
        if intr is None or obs.depth is None:
            return False
        camera = Camera(
            width=intr.width,
            height=intr.height,
            fov_deg=math.degrees(2 * math.atan(intr.width / (2 * intr.fx))),
            pitch_rad=self.camera_pitch_rad,
        )
        pixels, z = camera.project(np.array([self._tracked_target]), origin, obs.yaw_rad)
        u, v = pixels[0]
        if not (z[0] > 0.2 and 0 <= u < intr.width and 0 <= v < intr.height):
            return False
        depth = global_store().get(obs.depth.uri)
        if depth is None:
            return False
        d = _depth_at(np.asarray(depth), u, v, patch=0)
        # Live geometry verifies that the retained target is still in the image
        # and not occluded; no RGB color detector or simulator semantic hits.
        return d is not None and abs(d - z[0]) <= 0.3

    def observe_task_evidence(self, observation, scratch):
        if self._initial_position is None:
            self._initial_position = observation.position
        now = observation.t_sim_ns
        if self._hover_last_ns is not None and now <= self._hover_last_ns:
            return
        self._latest_hover_obs = observation
        dt = (now - self._hover_last_ns) / 1e9 if self._hover_last_ns is not None else 0
        stable = self._hover_point is None or (
            self._tracked_target is not None
            and np.linalg.norm(self._tracked_target - self._hover_point) <= 0.25
        )
        good = self._hover_geometry(observation) and stable
        interval_good = good and (self._previous_hover_good or not self.stable_hover_reference)
        self._hover_s = self._hover_s + dt if interval_good and 0 < dt <= 0.1 else 0.0
        self._previous_hover_good = good
        self._hover_last_ns = now
        self._hover_point = None if self._tracked_target is None else self._tracked_target.copy()

    def stop_still_supported(self, observation):
        if self.stable_hover_reference:
            if observation.t_sim_ns != self._hover_last_ns:
                return False
            if self._hover_point is not None and (
                self._tracked_target is None
                or np.linalg.norm(self._tracked_target - self._hover_point) > 0.25
            ):
                return False
        return self._hover_s >= 2.0 - 1e-9 and self._hover_geometry(observation)

    def _live_hover_result(self, result):
        """Resolve completion at return time, with dwell and geometry at one timestamp."""
        if not self.stable_hover_reference:
            return result
        obs = self._latest_hover_obs
        supported = obs is not None and self.stop_still_supported(obs)
        label = ProgressLabel.STOP if supported else result.label
        if not supported and label is ProgressLabel.STOP:
            label = ProgressLabel.CONTINUE
        return result.model_copy(
            update={
                "label": label,
                "t_sim_ns": obs.t_sim_ns if obs is not None else result.t_sim_ns,
                "observation_seq": obs.seq if obs is not None else result.observation_seq,
                "evidence": result.evidence
                + f"; grounding_source_seq={result.observation_seq}"
                + f"; live_hover_supported={supported}; live_hover_seq={obs.seq if obs else None}",
            }
        )

    def _grounding_context(self, ctx, prompt, images):
        if self._reference_image is None:
            return (
                prompt
                + " Point near the center of the target body, not its foot or an image corner.",
                images,
            )
        prompt = (
            "Two camera views from the SAME flight: FIRST is an earlier reference where "
            "the requested object was identified; SECOND is the CURRENT view. "
            "Track object identity across approach/zoom. A nearby object can be cropped "
            "and fill the current frame; lack of its full outline alone does not mean absence. "
            "History alone cannot prove current visibility: check current appearance too. "
            "Report visible and u,v for the SECOND image ONLY; choose a point near the "
            "center of the visible target body, not an image corner. " + prompt
        )
        return prompt, [self._reference_image, images[-1]]

    async def assess(self, ctx):
        image = global_store().get(ctx.observation.rgb.uri) if ctx.observation.rgb else None
        snapshot = _encode_png(image) if image is not None else None
        result = await super().assess(ctx)
        if (
            self._reference_image is None
            and snapshot is not None
            and self._tracked_target_t_ns == ctx.observation.t_sim_ns
            and self._tracked_target is not None
        ):
            self._reference_image = snapshot
            self._reference_seq = ctx.observation.seq
        if self._approach is None and self._tracked_target is not None:
            p = (
                self._initial_position if self.stable_hover_reference else None
            ) or ctx.observation.position
            delta = self._tracked_target - np.array([p.x, p.y, p.z])
            delta[2] = 0.0
            if np.linalg.norm(delta) > 0.1:
                self._approach = delta / np.linalg.norm(delta)
        result = self._live_hover_result(result)
        return result.model_copy(
            update={
                "evidence": result.evidence
                + f"; hover_streak_s={self._hover_s:.3f}; required_hover_s=2; "
                + f"live_view_depth_check=true; reference_seq={self._reference_seq}"
            }
        )
