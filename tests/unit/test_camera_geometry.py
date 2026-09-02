"""Simulator-independent camera bearing and triangulation geometry."""

from __future__ import annotations

import numpy as np

from uavlab.core.camera import Camera, triangulate_rays


def test_two_calibrated_camera_rays_recover_a_world_point():
    camera = Camera(width=224, height=224, fov_deg=90.0, pitch_rad=-0.15)
    target = np.array([12.0, 2.0, 3.0])
    origin_a = np.array([0.0, -2.0, 3.0])
    origin_b = np.array([2.0, -2.0, 3.0])
    yaw_a = float(np.arctan2(target[1] - origin_a[1], target[0] - origin_a[0]))
    yaw_b = float(np.arctan2(target[1] - origin_b[1], target[0] - origin_b[0]))

    pixel_a, _ = camera.project(target[None, :], origin_a, yaw_a)
    pixel_b, _ = camera.project(target[None, :], origin_b, yaw_b)
    ray_a = camera.ray_world(float(pixel_a[0, 0]), float(pixel_a[0, 1]), yaw_a)
    ray_b = camera.ray_world(float(pixel_b[0, 0]), float(pixel_b[0, 1]), yaw_b)

    result = triangulate_rays(origin_a, ray_a, origin_b, ray_b)
    assert result is not None
    midpoint, gap_m, _, _ = result
    assert gap_m < 1e-8
    assert np.allclose(midpoint, target, atol=1e-7)


def test_parallel_rays_do_not_invent_a_range():
    result = triangulate_rays(
        np.array([0.0, 0.0, 3.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 3.0]),
        np.array([1.0, 0.0, 0.0]),
    )
    assert result is None
