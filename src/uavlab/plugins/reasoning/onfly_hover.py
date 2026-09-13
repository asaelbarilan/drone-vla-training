"""Opt-in D-108 hover validator using VLM RGB-D identity and live odometry only."""

import math

import numpy as np

from uavlab.core.camera import Camera
from uavlab.core.frame_store import global_store
from uavlab.core.registry import register
from uavlab.plugins.reasoning.onfly import OnFlyMonitor, _depth_at


@register("monitor", "onfly_hover_monitor")
class OnFlyHoverMonitor(OnFlyMonitor):
    def reset(self, mission, seed):
        super().reset(mission, seed)
        if "Hold for 2 continuous seconds" not in mission.instruction:
            raise ValueError("hover monitor requires the explicit D-108 hover contract")
        self._approach = None
        self._hover_s = 0.0
        self._hover_last_ns = None
        self._hover_point = None

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
        cross = float(np.linalg.norm(delta - along * self._approach))
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
        now = observation.t_sim_ns
        if self._hover_last_ns is not None and now <= self._hover_last_ns:
            return
        dt = (now - self._hover_last_ns) / 1e9 if self._hover_last_ns is not None else 0
        stable = self._hover_point is None or (
            self._tracked_target is not None
            and np.linalg.norm(self._tracked_target - self._hover_point) <= 0.25
        )
        good = self._hover_geometry(observation) and stable
        self._hover_s = self._hover_s + dt if good and 0 < dt <= 0.1 else 0.0
        self._hover_last_ns = now
        self._hover_point = None if self._tracked_target is None else self._tracked_target.copy()

    def stop_still_supported(self, observation):
        return self._hover_s >= 2.0 - 1e-9 and self._hover_geometry(observation)

    async def assess(self, ctx):
        result = await super().assess(ctx)
        if self._approach is None and self._tracked_target is not None:
            p = ctx.observation.position
            delta = self._tracked_target - np.array([p.x, p.y, p.z])
            if np.linalg.norm(delta) > 0.1:
                self._approach = delta / np.linalg.norm(delta)
        return result.model_copy(
            update={
                "evidence": result.evidence
                + f"; hover_streak_s={self._hover_s:.3f}; required_hover_s=2; live_view_depth_check=true"
            }
        )
