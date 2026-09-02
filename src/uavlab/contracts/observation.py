"""The observation contract — the simulator-independence boundary.

Every environment adapter (deterministic grid, dataset replay, Project AirSim,
PX4/Gazebo) must produce exactly this.  Nothing downstream is allowed to know
which adapter it came from.
"""

from __future__ import annotations

from typing import Literal

from uavlab.contracts.common import Frame, StrictModel, Vec3

CoarseGoalDirection = Literal[
    "straight ahead",
    "forward-right",
    "to your right",
    "to your right rear",
    "forward-left",
    "to your left",
    "to your left rear",
]


class CameraIntrinsics(StrictModel):
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float


class SensorRef(StrictModel):
    """A reference to sensor data rather than the data itself.

    Images are referenced, not embedded, so that an ObservationPacket stays
    cheap to log, hash and compare.  ``digest`` makes replay verifiable and is
    what the FeatureCache keys on.
    """

    kind: str
    """e.g. "rgb", "depth", "semantic"."""
    uri: str
    """Adapter-resolvable locator; may be an in-memory handle like ``mem://...``."""
    digest: str
    """Stable content hash.  Two identical frames must produce identical digests."""
    shape: tuple[int, ...] | None = None


class IMUSample(StrictModel):
    angular_velocity: Vec3
    linear_acceleration: Vec3


class SemanticHit(StrictModel):
    """Detector output produced by the *sensing rig*, not by a perception plugin.

    Lightweight and replay adapters have no renderable imagery, so the open-set
    detector that would normally run on the camera is part of the sensor model
    instead.  Vision-rich adapters (Project AirSim, PX4/Gazebo) leave this
    empty and the perception plugin computes detections from ``rgb``.

    This is a *sensor* channel and obeys field of view, range and occlusion.
    It is emphatically not ground truth: what the vehicle cannot see is not
    reported here.
    """

    label: str
    score: float
    position: Vec3
    distance_m: float
    bearing_rad: float


class ObservationPacket(StrictModel):
    """One synchronised sensing instant.

    ``seq`` and ``t_sim_ns`` are the anchors for the entire staleness
    accounting: a decision remembers which packet produced it, so the runtime
    can later report how obsolete the world was when that decision executed.
    """

    seq: int
    """Monotonic observation counter.  Never reused within an episode."""
    t_sim_ns: int
    """Simulation timestamp of the sensing instant."""
    t_wall_ns: int
    """Wall-clock timestamp; differs from ``t_sim_ns`` under fake clocks."""

    position: Vec3
    velocity: Vec3
    yaw_rad: float
    frame: Frame = Frame.ENU

    rgb: SensorRef | None = None
    rgb_down: SensorRef | None = None
    """Optional downward RGB camera, independent of the forward ``rgb`` view."""
    depth: SensorRef | None = None
    intrinsics: CameraIntrinsics | None = None
    imu: IMUSample | None = None
    semantic_hits: tuple[SemanticHit, ...] = ()
    """Sensor-side detections; see :class:`SemanticHit`. Subject to FOV and range."""
    free_range_m: float = float("inf")
    """Distance to the nearest obstacle along the current heading (range sensor)."""
    range_rays: tuple[float, ...] = ()
    """Horizontal depth fan, one distance per bearing in :attr:`ray_bearings_rad`.

    This is the geometric sensing channel.  Turning it into an occupancy hint is
    the perception plugin's job, and using that hint is the planner's job — the
    semantic policy never sees raw ranges, so "avoided the wall" can never be
    credited to the foundation model by accident.
    """
    ray_bearings_rad: tuple[float, ...] = ()
    """Body-relative bearings of :attr:`range_rays`, ascending."""
    vertical_clearance_m: float = float("inf")

    battery_frac: float = 1.0

    coarse_goal_direction: CoarseGoalDirection | None = None
    """Bucketed target-relative navigation prior, never an exact bearing.

    This channel exists for tasks that explicitly provide a target-location
    prior, as AeroVLA assumes. Unknown-location object search leaves it
    ``None``. The environment may use localization to produce the bucket, but
    policies never receive the target coordinate or continuous angle.
    """

    privileged: dict[str, object] | None = None
    """Ground-truth channel for oracle/fake plugins only.

    Real adapters and real models must leave this ``None``.  It exists so that
    C0 (the oracle control ceiling) is expressible without a special-case code
    path, and the orchestrator refuses to populate it unless the architecture
    config sets ``allow_privileged_observations``.
    """
