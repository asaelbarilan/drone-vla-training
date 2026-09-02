"""The camera model, shared by every simulator adapter and every policy.

Deliberately outside `adapters/`. A pinhole projection is not a property of one
simulator - it is the geometry that turns "the model pointed at that pixel" into
a world point, and it is the same arithmetic whether the pixels came from a
rasteriser, from AirSim, or from a real camera.

It lived in `adapters/gym/render.py`, which meant the point-and-fly policy
imported the toy simulator's rendering module to do its own geometry. The policy
could therefore not run against any other simulator, and this was the *only*
such leak in the runtime - found by a boundary test written while planning the
AirSim port, rather than by the port failing on contact.

Adapters supply intrinsics through `ObservationPacket`; policies unproject with
them. Neither needs to know where the pixels came from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class Camera:
    """Forward-facing pinhole camera rigidly mounted to the airframe."""

    width: int = 224
    height: int = 224
    fov_deg: float = 90.0
    pitch_rad: float = -0.15
    """Slight downward tilt, as a survey camera would be mounted."""

    @property
    def focal_px(self) -> float:
        return (self.width / 2.0) / math.tan(math.radians(self.fov_deg) / 2.0)

    def project(self, points_world: np.ndarray, position: np.ndarray, yaw: float) -> tuple[np.ndarray, np.ndarray]:
        """World points (N,3) -> pixel coords (N,2) and camera depth (N,).

        Depth is returned separately so the caller can cull behind-camera points
        and sort by distance; a projected pixel alone cannot tell you either.
        """
        rel = points_world - position
        cos_y, sin_y = math.cos(-yaw), math.sin(-yaw)
        # Rotate into a body frame whose +x axis is the direction of travel.
        fwd = rel[:, 0] * cos_y - rel[:, 1] * sin_y
        left = rel[:, 0] * sin_y + rel[:, 1] * cos_y
        up = rel[:, 2].copy()

        cos_p, sin_p = math.cos(-self.pitch_rad), math.sin(-self.pitch_rad)
        fwd_p = fwd * cos_p - up * sin_p
        up_p = fwd * sin_p + up * cos_p

        depth = fwd_p
        safe = np.where(np.abs(depth) < 1e-6, 1e-6, depth)
        u = self.width / 2.0 - self.focal_px * (left / safe)
        v = self.height / 2.0 - self.focal_px * (up_p / safe)
        return np.stack([u, v], axis=-1), depth

    def unproject(
        self, u: float, v: float, depth_m: float, position: np.ndarray, yaw: float
    ) -> np.ndarray:
        """Pixel + assumed depth -> a world point. Exact inverse of `project`.

        This is what turns "the model pointed at that part of the image" into a
        waypoint, which is the whole mechanism of the point-and-fly family: the
        VLM never emits a coordinate, it emits a *pixel*, and the geometry is
        done by code that can be checked.

        Depth cannot be recovered from one pixel, so the caller supplies it —
        normally a fixed hop distance. That is a real limitation of the design,
        not an implementation shortcut, and it is why these policies propose a
        direction repeatedly rather than one final destination.
        """
        left = (self.width / 2.0 - u) * depth_m / self.focal_px
        up_p = (self.height / 2.0 - v) * depth_m / self.focal_px
        fwd_p = depth_m

        cos_p, sin_p = math.cos(-self.pitch_rad), math.sin(-self.pitch_rad)
        fwd = fwd_p * cos_p + up_p * sin_p
        up = -fwd_p * sin_p + up_p * cos_p

        cos_y, sin_y = math.cos(-yaw), math.sin(-yaw)
        rel_x = fwd * cos_y + left * sin_y
        rel_y = -fwd * sin_y + left * cos_y
        return position + np.array([rel_x, rel_y, up])

    def ray_world(self, u: float, v: float, yaw: float) -> np.ndarray:
        """Return the unit world-frame bearing for one image pixel.

        Unlike :meth:`unproject`, this makes no range assumption. It is the
        quantity a second view can intersect using ordinary vehicle odometry.
        """
        origin = np.zeros(3, dtype=float)
        point = self.unproject(u, v, 1.0, origin, yaw)
        norm = float(np.linalg.norm(point))
        if norm < 1e-12:
            raise ValueError("pixel produced a zero-length camera ray")
        return point / norm


def triangulate_rays(
    origin_a: np.ndarray,
    direction_a: np.ndarray,
    origin_b: np.ndarray,
    direction_b: np.ndarray,
) -> tuple[np.ndarray, float, float, float] | None:
    """Closest-point triangulation for two forward camera rays.

    Returns ``(midpoint, ray_gap_m, distance_a_m, distance_b_m)``. ``None``
    means the rays are parallel or the closest point lies behind a camera.
    Skew rays are expected with pixel noise; callers decide how much gap is
    admissible for their sensor/model combination.
    """
    p = np.asarray(origin_a, dtype=float)
    q = np.asarray(origin_b, dtype=float)
    u = np.asarray(direction_a, dtype=float)
    v = np.asarray(direction_b, dtype=float)
    u_norm = float(np.linalg.norm(u))
    v_norm = float(np.linalg.norm(v))
    if u_norm < 1e-12 or v_norm < 1e-12:
        return None
    u = u / u_norm
    v = v / v_norm

    w0 = p - q
    b = float(np.dot(u, v))
    d = float(np.dot(u, w0))
    e = float(np.dot(v, w0))
    denominator = 1.0 - b * b
    if denominator < 1e-9:
        return None

    distance_a = (b * e - d) / denominator
    distance_b = (e - b * d) / denominator
    if distance_a <= 0.0 or distance_b <= 0.0:
        return None

    point_a = p + distance_a * u
    point_b = q + distance_b * v
    midpoint = (point_a + point_b) / 2.0
    gap = float(np.linalg.norm(point_a - point_b))
    return midpoint, gap, float(distance_a), float(distance_b)
