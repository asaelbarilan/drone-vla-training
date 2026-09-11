"""D-86: camera yaw can differ while translational commands stay identical."""

import math
from types import SimpleNamespace

import pytest

from uavlab.contracts import Vec3
from uavlab.plugins.control.mock import MockVelocityController


def test_goal_yaw_preserves_avoidance_translation_and_rate_limit():
    ctx = SimpleNamespace(
        t_sim_ns=0, observation=SimpleNamespace(position=Vec3(x=0, y=0, z=3), yaw_rad=0.0)
    )
    trajectory = SimpleNamespace(
        points=[SimpleNamespace(position=Vec3(x=0, y=5, z=3))],
        metadata={"semantic_goal_xyz": "5,0,3"},
        source_decision_id="test",
    )
    baseline = MockVelocityController(max_yaw_rate_rps=0.4).track(trajectory, ctx)
    changed = MockVelocityController(max_yaw_rate_rps=0.4, face_semantic_goal=True).track(
        trajectory, ctx
    )
    assert changed.velocity == baseline.velocity
    assert baseline.yaw_rate_rps == pytest.approx(0.4)
    assert changed.yaw_rate_rps == pytest.approx(0.0)
    ctx.observation.yaw_rad = math.pi
    assert (
        abs(
            MockVelocityController(max_yaw_rate_rps=0.4, face_semantic_goal=True)
            .track(trajectory, ctx)
            .yaw_rate_rps
        )
        <= 0.4
    )


def test_missing_goal_is_explicit_error_only_for_opt_in():
    ctx = SimpleNamespace(
        t_sim_ns=0, observation=SimpleNamespace(position=Vec3(x=0, y=0, z=3), yaw_rad=0)
    )
    trajectory = SimpleNamespace(
        points=[SimpleNamespace(position=Vec3(x=4, y=0, z=3))],
        metadata={},
        source_decision_id="test",
    )
    MockVelocityController().track(trajectory, ctx)
    with pytest.raises(ValueError, match="requires"):
        MockVelocityController(face_semantic_goal=True).track(trajectory, ctx)
