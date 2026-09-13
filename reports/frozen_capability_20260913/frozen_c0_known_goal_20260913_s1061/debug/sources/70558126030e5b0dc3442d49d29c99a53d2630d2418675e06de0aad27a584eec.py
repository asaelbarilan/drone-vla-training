"""Perception plugins.

Perception is held *equivalent* across the first architecture sweep on purpose:
detector architecture is a deployment parameter, and letting it vary would turn
architecture results into detector results.  What these plugins do is convert
sensor channels into the two things downstream components are allowed to use —
semantic detections and a geometric occupancy hint — and nothing else.
"""

from __future__ import annotations

import math
from typing import Any

from uavlab.contracts import (
    Detection,
    FeatureRef,
    MissionSpec,
    ObservationPacket,
    OccupancyHint,
    PerceptionState,
    Vec3,
)
from uavlab.core.registry import register
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import InferenceRequest


def _occupancy(obs: ObservationPacket, drone_radius_m: float) -> OccupancyHint:
    """Turn the depth fan into the planner's geometric evidence."""
    if not obs.range_rays:
        return OccupancyHint(free_radius_m=obs.free_range_m)
    nearest_idx = min(range(len(obs.range_rays)), key=lambda i: obs.range_rays[i])
    nearest_range = obs.range_rays[nearest_idx]
    bearing = obs.ray_bearings_rad[nearest_idx] + obs.yaw_rad
    nearest = Vec3(
        x=obs.position.x + nearest_range * math.cos(bearing),
        y=obs.position.y + nearest_range * math.sin(bearing),
        z=obs.position.z,
    )
    blocked = tuple(
        (math.cos(b + obs.yaw_rad), math.sin(b + obs.yaw_rad), 0.0)
        for b, r in zip(obs.ray_bearings_rad, obs.range_rays, strict=True)
        if r < max(2.0, drone_radius_m * 4.0)
    )
    return OccupancyHint(
        free_radius_m=min(obs.range_rays),
        nearest_obstacle=nearest,
        nearest_obstacle_distance_m=nearest_range,
        blocked_directions=blocked,
    )


@register("perception", "identity")
class IdentityPerception:
    """Pass sensor detections through, plus geometry. No learned component.

    ``identity`` here means "adds no perceptual capability of its own" — it is
    the neutral baseline that keeps perception constant while semantic
    architecture varies.
    """

    def __init__(self, **params: Any) -> None:
        self.min_score = float(params.get("min_score", 0.0))
        self.drone_radius_m = float(params.get("drone_radius_m", 0.4))
        self.charge_latency = bool(params.get("charge_latency", False))
        """Charge a nominal detector cost to the clock.

        Default off. This plugin runs no model, so against a real inference
        backend "charging" it means sending an empty prompt to a real network
        and waiting seconds for a reply nobody reads. Simulated profiles opt in
        explicitly, where the cost is pure bookkeeping."""
        self.encoder_id = str(params.get("encoder_id", "shared_vit"))
        self._services: RuntimeServices | None = None

    @property
    def name(self) -> str:
        return "identity"

    def bind_runtime(self, services: RuntimeServices) -> None:
        self._services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        return None

    async def perceive(self, observation: ObservationPacket, mission: MissionSpec) -> PerceptionState:
        if self.charge_latency and self._services is not None and self._services.inference is not None:
            await self._services.inference.invoke(
                InferenceRequest(
                    model_id="detector",
                    role="perception",
                    prompt_hash=observation.rgb.digest if observation.rgb else "none",
                    image_count=1,
                    observation_seq=observation.seq,
                )
            )

        detections = tuple(
            Detection(
                label=hit.label,
                score=hit.score,
                position=hit.position,
                distance_m=hit.distance_m,
            )
            for hit in observation.semantic_hits
            if hit.score >= self.min_score
        )
        features = (
            FeatureRef(
                encoder_id=self.encoder_id,
                observation_seq=observation.seq,
                digest=observation.rgb.digest,
            )
            if observation.rgb
            else None
        )
        # Uncertainty is "no usable visual evidence", which is what an event
        # trigger should react to — not "the model felt unsure".
        best = max((d.score for d in detections), default=0.0)
        return PerceptionState(
            observation_seq=observation.seq,
            t_sim_ns=observation.t_sim_ns,
            detections=detections,
            features=features,
            geometry=_occupancy(observation, self.drone_radius_m),
            uncertainty=float(max(0.0, 1.0 - best)),
        )


@register("perception", "noisy")
class NoisyPerception(IdentityPerception):
    """Identity perception with a configurable detection dropout.

    Used to check that an architecture's advantage is not an artefact of perfect
    sensing: if a monitor only helps when detections are flawless, it is not
    doing the job it is credited with.
    """

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.dropout = float(params.get("dropout", 0.15))
        self._rng = None

    @property
    def name(self) -> str:
        return "noisy"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        import numpy as np

        self._rng = np.random.default_rng(seed + 4242)

    async def perceive(self, observation: ObservationPacket, mission: MissionSpec) -> PerceptionState:
        state = await super().perceive(observation, mission)
        if self._rng is None or self.dropout <= 0.0:
            return state
        kept = tuple(d for d in state.detections if float(self._rng.random()) >= self.dropout)
        best = max((d.score for d in kept), default=0.0)
        return state.model_copy(
            update={"detections": kept, "uncertainty": float(max(0.0, 1.0 - best))}
        )
