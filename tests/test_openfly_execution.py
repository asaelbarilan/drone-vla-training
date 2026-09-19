import math

import pytest

from uavlab.training.openfly_execution import (
    advance_pose,
    airsim_pose_components,
    navigation_metrics,
)


def test_codebook_amplitudes_are_not_physical_amplitudes():
    assert advance_pose([0, 0, 0, 0], 4) == (0, 0, 3, 0)
    assert advance_pose([0, 0, 0, 0], 6) == (0, 3, 0, 0)
    assert advance_pose([0, 0, 0, 0], 2)[3] == pytest.approx(math.pi / 6)


def test_rotated_translation_and_turn_wrap():
    assert advance_pose([1, 2, 3, math.pi / 2], 9) == pytest.approx((1, 11, 3, math.pi / 2))
    assert advance_pose([1, 2, 3, math.pi / 2], 6) == pytest.approx((-2, 2, 3, math.pi / 2))
    assert advance_pose([0, 0, 0, math.pi], 2)[3] == pytest.approx(-5 * math.pi / 6)


@pytest.mark.parametrize("action", [None, -1, 10, True, 1.0, "stop"])
def test_invalid_action_is_not_stop(action):
    with pytest.raises(ValueError):
        advance_pose([0, 0, 0, 0], action)


def test_coordinate_conversion():
    assert airsim_pose_components([2, -4, 7, math.pi / 3]) == (2, 4, -7, -math.pi / 3)


def test_reject_nonfinite_pose():
    with pytest.raises(ValueError):
        advance_pose([0, 0, float("nan"), 0], 0)


@pytest.mark.parametrize(
    "reason", ["timeout", "invalid_model_output", "renderer_error", "collision"]
)
def test_near_goal_error_is_not_success(reason):
    metrics = navigation_metrics([[0, 0, 0, 0], [9, 0, 0, 0]], [10, 0, 0], reason, 2)
    assert metrics["legacy_endpoint_success"]
    assert metrics["oracle_goal_reached"]
    assert not metrics["success_with_stop"]
    assert metrics["path_length"] == 9


def test_reaching_then_leaving_goal_only_counts_oracle():
    metrics = navigation_metrics([[0, 0, 0, 0], [9, 0, 0, 0], [20, 0, 0, 0]], [10, 0, 0], "stop", 2)
    assert metrics["oracle_goal_reached"]
    assert not metrics["success_with_stop"]
    assert navigation_metrics([[9, 0, 0, 0]], [10, 0, 0], "stop", 2)["success_with_stop"]
