"""Geometry invariants of the deterministic screening environment."""

from __future__ import annotations

import asyncio

import pytest

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import MissionSpec, TaskFamily


def test_clutter_obstacles_are_ground_attached_vertical_columns() -> None:
    environment = DeterministicEnv(scene="clutter", n_obstacles=10)
    mission = MissionSpec(
        mission_id="column-geometry",
        instruction="reach the target",
        task_family=TaskFamily.LONG_HORIZON_NAV,
    )

    asyncio.run(environment.reset(mission, seed=1022))

    assert environment.obstacles
    assert all(
        obstacle.center[2] - obstacle.half[2] == pytest.approx(0.0)
        for obstacle in environment.obstacles
    )
