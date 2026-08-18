"""Perception output.

Kept separate from :class:`MemorySnapshot` on purpose: this is *what is visible
now*, not *what the mission remembers*.  Conflating the two is the mistake the
design-space study warns about.
"""

from __future__ import annotations

from pydantic import Field

from uavlab.contracts.common import StrictModel, Vec3


class Detection(StrictModel):
    """One open-vocabulary detection."""

    label: str
    score: float
    bbox_xyxy: tuple[float, float, float, float] | None = None
    position: Vec3 | None = None
    """Metric position when depth is available; ``None`` for image-only detectors."""
    distance_m: float | None = None


class FeatureRef(StrictModel):
    """A handle to reusable visual features.

    Feature *sharing* is an efficiency experiment, not an architecture axis, so
    the contract carries a reference and the FeatureCache decides whether two
    semantic agents actually share the tensor.
    """

    encoder_id: str
    observation_seq: int
    digest: str
    dim: int | None = None


class OccupancyHint(StrictModel):
    """Local geometry for the planner.

    This is the flight controller's geometric world model.  It is deliberately
    *not* part of MemorySnapshot: an ESDF that avoids walls must never be
    counted as "the VLM has memory".
    """

    free_radius_m: float
    nearest_obstacle: Vec3 | None = None
    nearest_obstacle_distance_m: float | None = None
    blocked_directions: tuple[tuple[float, float, float], ...] = ()


class PerceptionState(StrictModel):
    """Everything the current frame supports believing."""

    observation_seq: int
    t_sim_ns: int
    detections: tuple[Detection, ...] = ()
    features: FeatureRef | None = None
    geometry: OccupancyHint | None = None
    uncertainty: float = 0.0
    """0 = confident, 1 = no usable visual evidence.  Drives event triggers."""
    notes: dict[str, str] = Field(default_factory=dict)
