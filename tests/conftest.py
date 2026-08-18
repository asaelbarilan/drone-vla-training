"""Shared fixtures.

Every test in this repository must run with no CUDA, no ROS, no Gazebo, no
network and no model download.  That is not a convenience goal: architecture
logic that can only be tested on a GPU box does not get tested.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.core.results import EpisodeResult

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"

ALL_ARCHITECTURES = [f"c{i}" for i in range(15)]
SENTINEL_ARCHITECTURES = ["c1", "c2", "c3", "c5", "c6", "c7", "c8", "c12"]
"""The eight configurations the specification requires first.

They span every axis: skill / waypoint / direct-VLA authority, verifier on and
off, shield on and off, persistent monitoring versus event-triggered recovery,
single action versus chunk, and periodic versus asynchronous scheduling.
"""


@pytest.fixture(scope="session")
def config_root() -> Path:
    return CONFIG_ROOT


@pytest.fixture
def arch_factory(config_root):
    def _load(name: str):
        return load_architecture(name, config_root)

    return _load


@pytest.fixture
def env_factory(config_root):
    def _load(name: str):
        return load_environment(name, config_root)

    return _load


def run_one(arch, env, seed: int = 1, out_dir: Path | None = None) -> tuple[EpisodeResult, Orchestrator]:
    """Run a single episode and hand back the orchestrator for log inspection."""
    orchestrator = Orchestrator(
        arch, env, EpisodeSpec(episode_id=f"test_{arch.id}_{seed}", seed=seed), out_dir=out_dir
    )
    result = asyncio.run(orchestrator.run())
    return result, orchestrator


@pytest.fixture
def runner():
    return run_one
