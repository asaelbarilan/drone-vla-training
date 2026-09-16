from __future__ import annotations

import json
import math

import pytest

from uavlab.contracts import ControlCommand, Frame, Vec3
from uavlab.core.frames import enu_to_body
from uavlab.training.direct_vla_contract import (
    HORIZONTAL_RANGE_MPS,
    YAW_RATE_RANGE_RPS,
    DirectVLAOutputError,
    DirectVLATarget,
    action_from_target,
    dequantize_symmetric,
    parse_target,
    quantize_symmetric,
    target_from_command,
    target_json,
)


def command(vx: float, vy: float, vz: float, yaw_rate: float) -> ControlCommand:
    return ControlCommand(
        t_sim_ns=0,
        velocity=Vec3(x=vx, y=vy, z=vz, frame=Frame.ENU),
        yaw_rate_rps=yaw_rate,
    )


def test_zero_is_an_exact_bin_centre() -> None:
    assert quantize_symmetric(0.0, HORIZONTAL_RANGE_MPS) == 32
    assert dequantize_symmetric(32, HORIZONTAL_RANGE_MPS) == 0.0
    assert dequantize_symmetric(32, YAW_RATE_RANGE_RPS) == 0.0


@pytest.mark.parametrize("yaw", [0.0, math.pi / 2, -2.1])
def test_command_round_trip_preserves_body_velocity_and_yaw(yaw: float) -> None:
    source = command(2.25, -1.5, 0.75, 1.4)
    target = target_from_command(source, yaw)
    action = action_from_target(target, yaw, duration_s=0.1)
    assert action is not None
    source_body = enu_to_body(source.velocity, yaw)
    decoded_body = enu_to_body(action.velocity, yaw)
    half_velocity_bin = 10.0 / 64 / 2
    for actual, expected in zip(decoded_body.as_tuple(), source_body.as_tuple(), strict=True):
        assert actual == pytest.approx(expected, abs=half_velocity_bin + 1e-9)
    assert action.yaw_rate_rps == pytest.approx(1.4, abs=3.0 / 64 / 2 + 1e-9)
    assert action.duration_s == 0.1


def test_hover_and_stop_are_distinct() -> None:
    hold = target_from_command(command(0.0, 0.0, 0.0, 0.0), 0.7)
    stop = target_from_command(command(0.0, 0.0, 0.0, 0.0), 0.7, terminal=True)
    assert hold == DirectVLATarget(32, 32, 32, 32, False)
    assert stop == DirectVLATarget(32, 32, 32, 32, True)
    hold_action = action_from_target(hold, 0.7, duration_s=0.2)
    assert hold_action is not None and hold_action.velocity.norm() == 0.0
    assert action_from_target(stop, 0.7, duration_s=0.2) is None


def test_yaw_range_represents_full_benchmark_limit_without_clipping() -> None:
    left = target_from_command(command(0.0, 0.0, 0.0, 1.5), 0.0)
    right = target_from_command(command(0.0, 0.0, 0.0, -1.5), 0.0)
    assert left.yaw_rate_bin == 64
    assert right.yaw_rate_bin == 0


def test_json_parser_is_strict_and_stop_cannot_carry_motion() -> None:
    target = DirectVLATarget(40, 20, 32, 60, False)
    assert parse_target(target_json(target)) == target
    invalid = json.loads(target_json(target))
    invalid["extra"] = 1
    with pytest.raises(DirectVLAOutputError, match="exactly"):
        parse_target(json.dumps(invalid))
    with pytest.raises(DirectVLAOutputError, match="zero motion"):
        parse_target(
            '{"vx_body_bin":40,"vy_body_bin":32,"vz_body_bin":32,"yaw_rate_bin":32,"stop":true}'
        )
    with pytest.raises(DirectVLAOutputError, match="integers"):
        parse_target(
            '{"vx_body_bin":true,"vy_body_bin":32,"vz_body_bin":32,"yaw_rate_bin":32,"stop":false}'
        )


def test_decoder_rejects_nonpositive_duration() -> None:
    with pytest.raises(ValueError, match="positive"):
        action_from_target(DirectVLATarget(32, 32, 32, 32), 0.0, duration_s=0.0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "1"])
def test_invalid_numeric_values_rejected_before_commands(value) -> None:
    with pytest.raises(ValueError, match="finite"):
        quantize_symmetric(value, HORIZONTAL_RANGE_MPS)
    with pytest.raises(ValueError, match="finite"):
        action_from_target(DirectVLATarget(32, 32, 32, 32), value, duration_s=0.1)
    with pytest.raises(ValueError, match="finite"):
        action_from_target(DirectVLATarget(32, 32, 32, 32), 0.0, duration_s=value)


@pytest.mark.parametrize("value", [-5.01, 5.01])
def test_outside_teacher_vocabulary_rejected_without_clipping(value) -> None:
    with pytest.raises(ValueError, match="no silent clipping"):
        quantize_symmetric(value, HORIZONTAL_RANGE_MPS)


@pytest.mark.parametrize("duration", [0.001, 0.07])
def test_horizon_cannot_silently_round_to_a_control_tick(duration) -> None:
    with pytest.raises(ValueError, match="control tick"):
        action_from_target(DirectVLATarget(32, 32, 32, 32), 0.0, duration_s=duration)


def test_frame_mismatch_and_moving_terminal_rejected() -> None:
    source = command(1.0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="both be ENU"):
        target_from_command(source.model_copy(update={"frame": Frame.NED}), 0.0)
    with pytest.raises(ValueError, match="zero-motion"):
        target_from_command(source, 0.0, terminal=True)
    with pytest.raises(ValueError, match="speed exceeds"):
        target_from_command(command(4.0, 4.0, 0.0, 0.0), 0.0)


def test_duplicate_json_fields_rejected() -> None:
    text = target_json(DirectVLATarget(32, 32, 32, 32))
    with pytest.raises(DirectVLAOutputError, match="duplicate"):
        parse_target(text.replace('"stop":false', '"stop":false,"stop":true'))


def test_source_yaw_axes_have_independent_physical_signs() -> None:
    action = action_from_target(DirectVLATarget(40, 40, 40, 40), math.pi / 2, duration_s=0.2)
    assert action is not None
    # Facing north: forward=north, left=west, up=up. Positive yaw is CCW.
    assert action.velocity.x == pytest.approx(-1.25)
    assert action.velocity.y == pytest.approx(1.25)
    assert action.velocity.z == pytest.approx(1.25)
    assert action.yaw_rate_rps == pytest.approx(0.375)
