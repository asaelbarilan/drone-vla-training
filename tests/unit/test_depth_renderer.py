"""Surface-depth contracts and preservation of the historical renderer."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from uavlab.adapters.gym.deterministic_env import DeterministicEnv, Landmark, Obstacle
from uavlab.adapters.gym.render import render_depth_frame
from uavlab.contracts import MissionSpec, TaskFamily
from uavlab.core.camera import Camera
from uavlab.core.frame_store import global_store


def box(center, half):
    return Obstacle(center=np.array(center, dtype=float), half=np.array(half, dtype=float))


def test_offscreen_top_corner_is_not_the_selected_wall_depth():
    # D-97's actual observation 800: the old minimum corner is outside the image.
    origin = np.array([18.226101626004965, 11.309535250854696, 2.56837719943317])
    yaw = 0.7919641306423534
    obstacle = box(
        [20.944656451448317, 12.765636915016001, 3.08961250204636],
        [1.54480625102318, 1.54480625102318, 3.08961250204636],
    )
    cam = Camera()
    legacy = render_depth_frame(origin, yaw, [obstacle], [], "target", cam)
    fixed = render_depth_frame(origin, yaw, [obstacle], [], "target", cam, renderer="box_ray_v2")
    ray = cam.unproject(111, 123, 1.0, np.zeros(3), yaw)
    expected = (obstacle.center[0] - obstacle.half[0] - origin[0]) / ray[0]
    assert legacy[123, 111] == pytest.approx(0.213216454, abs=1e-7)
    assert fixed[123, 111] == pytest.approx(expected, abs=1e-6)
    assert fixed[123, 111] == pytest.approx(1.731457139, abs=1e-6)
    assert np.ptp(fixed[121:126, 109:114]) > 0.05


def test_pitched_box_pixels_unproject_to_actual_faces():
    origin = np.array([0.0, 0.0, 3.0])
    obstacle = box([5.0, 0.0, 3.0], [1.0, 2.0, 3.0])
    cam = Camera(width=64, height=64, pitch_rad=-0.3)
    depth = render_depth_frame(origin, 0.12, [obstacle], [], "target", cam, renderer="box_ray_v2")
    ys, xs = np.where(np.isfinite(depth))
    assert len(xs) > 100
    for x, y in zip(xs[::29], ys[::29], strict=True):
        hit = cam.unproject(x, y, float(depth[y, x]), origin, 0.12)
        relative = np.abs(hit - obstacle.center) - obstacle.half
        assert relative.max() <= 1e-5
        assert np.abs(relative).min() < 1e-5


def test_foreground_drawn_box_occludes_background_depth():
    origin = np.array([0.0, 0.0, 3.0])
    near = box([5, 0, 3], [1, 1, 2])
    far = box([9, 0, 3], [1, 2, 3])
    mark = Landmark(np.array([8.0, 0.0, 3.0]), "target")
    cam = Camera(width=64, height=64, pitch_rad=0)
    for obstacles in ([near, far], [far, near]):
        depth = render_depth_frame(
            origin, 0, obstacles, [mark], "target", cam, renderer="box_ray_v2"
        )
        assert depth[32, 32] == 4.0


def test_missing_and_near_clipped_surfaces_are_not_invented():
    origin = np.array([0.0, 0.0, 3.0])
    cam = Camera(width=64, height=64, pitch_rad=0)
    too_close = box([0.2, 0, 3], [0.1, 2, 2])
    behind = box([-5, 0, 3], [1, 2, 2])
    depth = render_depth_frame(
        origin, 0, [too_close, behind], [], "target", cam, renderer="box_ray_v2"
    )
    assert np.isinf(depth[32, 32])
    assert not np.isnan(depth).any()
    empty = render_depth_frame(origin, 0, [], [], "target", cam, renderer="box_ray_v2")
    assert np.isinf(empty).all()


def test_billboard_depth_and_visibility_filter_are_unchanged():
    origin = np.array([0.0, 0.0, 3.0])
    cam = Camera(width=64, height=64, pitch_rad=0)
    marks = [Landmark(np.array([8.0, 0.0, 3.0]), "target")]
    for labels in (None, {"target"}, set()):
        old = render_depth_frame(origin, 0, [], marks, "target", cam, labels)
        new = render_depth_frame(origin, 0, [], marks, "target", cam, labels, renderer="box_ray_v2")
        assert np.array_equal(new, old)


def test_versioned_environment_preserves_rgb_and_range_sensors():
    async def capture(renderer):
        params = {"render": True, "render_depth": True}
        if renderer is not None:
            params["depth_renderer"] = renderer
        env = DeterministicEnv(**params)
        mission = MissionSpec(
            mission_id="depth-version",
            instruction="find target",
            task_family=TaskFamily.LONG_HORIZON_NAV,
        )
        obs = await env.reset(mission, 1061)
        rgb = np.array(global_store().get(obs.rgb.uri)).copy()
        depth = global_store().get(obs.depth.uri).copy()
        await env.close()
        return obs, rgb, depth

    old, old_rgb, old_depth = asyncio.run(capture(None))
    explicit, rgb, depth = asyncio.run(capture("legacy_corner"))
    fixed, fixed_rgb, _ = asyncio.run(capture("box_ray_v2"))
    assert old.depth.digest == explicit.depth.digest
    assert np.array_equal(old_depth, depth)
    assert np.array_equal(old_rgb, rgb) and np.array_equal(old_rgb, fixed_rgb)
    assert old.rgb.digest == fixed.rgb.digest
    assert old.depth.digest != fixed.depth.digest
    assert old.range_rays == fixed.range_rays


def test_unknown_depth_version_is_rejected():
    with pytest.raises(ValueError, match="Unknown depth renderer"):
        DeterministicEnv(depth_renderer="typo")
    with pytest.raises(ValueError, match="Unknown depth renderer"):
        render_depth_frame(np.zeros(3), 0, [], [], "target", renderer="typo")
