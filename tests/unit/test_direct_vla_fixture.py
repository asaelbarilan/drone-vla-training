from __future__ import annotations

import asyncio

import pytest

from uavlab.training.direct_vla_fixture import (
    goal_from_instruction,
    instruction_for,
    public_teacher,
    record,
    student_prompt,
)


def state(position=(0.0, 0.0, 3.0), velocity=(0.0, 0.0, 0.0), yaw=0.0):
    return {
        "position_enu_m": list(position),
        "velocity_enu_mps": list(velocity),
        "yaw_enu_rad": yaw,
    }


def test_public_instruction_changes_the_teacher_action():
    left = instruction_for((0.0, 4.0, 3.0))
    right = instruction_for((0.0, -4.0, 3.0))
    left_command, _, _ = public_teacher(left, state(), 0)
    right_command, _, _ = public_teacher(right, state(), 0)
    assert left_command.velocity.y == pytest.approx(1.5)
    assert right_command.velocity.y == pytest.approx(-1.5)
    assert left_command.yaw_rate_rps == 1.5
    assert right_command.yaw_rate_rps == -1.5


def test_terminal_requires_observed_slow_speed_not_distance_alone():
    instruction = instruction_for((0.0, 0.0, 3.0))
    command, terminal, evidence = public_teacher(instruction, state(velocity=(0.2, 0, 0)), 0)
    assert command.is_hold and not terminal
    assert evidence["speed_mps"] == pytest.approx(0.2)
    command, terminal, _ = public_teacher(instruction, state(), 0)
    assert command.is_hold and terminal
    command, terminal, _ = public_teacher(instruction, state(position=(1, 0, 3)), 0)
    assert not command.is_hold and not terminal


def test_instruction_coordinates_round_trip_and_prompt_declares_frames():
    goal = (1.3456789012, -6.98765, 2.4567)
    instruction = instruction_for(goal)
    assert goal_from_instruction(instruction) == goal
    prompt = student_prompt(instruction, state())
    assert instruction in prompt
    assert "Odometry:" in prompt and "level frame" in prompt
    assert "physical landing" in prompt


@pytest.mark.parametrize("seed", [1, 40, 999, 1060, 1064, 2000])
def test_record_rejects_forbidden_seeds_before_writing(tmp_path, seed):
    with pytest.raises(ValueError):
        asyncio.run(record(tmp_path, seed, 0, 0.0))
    assert not list(tmp_path.iterdir())
