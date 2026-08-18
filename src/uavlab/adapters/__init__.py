"""Environment adapters.

Two adapters import eagerly because they are pure Python: the deterministic
in-process environment and scene replay.  Having two real implementations is
deliberate — an adapter boundary with only one implementation behind it is an
assumption rather than an interface.

The live robotics adapters (PX4/Gazebo, Project AirSim, ROS 2, MAVSDK) load
lazily through :func:`load_adapter`, because importing them must never be a
precondition for running the core tests.  The repository has to work with no
ROS, no CUDA, no Gazebo and no network.
"""

from __future__ import annotations

import importlib

from uavlab.adapters.dataset_replay import replay as _scene_replay
from uavlab.adapters.gym import deterministic_env as _deterministic_env

OPTIONAL_ADAPTERS: dict[str, str] = {
    "project_airsim": "uavlab.adapters.project_airsim.adapter",
    "gazebo": "uavlab.adapters.gazebo.adapter",
    "px4": "uavlab.adapters.px4.adapter",
    "ros2": "uavlab.adapters.ros2.adapter",
    "mavsdk": "uavlab.adapters.mavsdk.adapter",
}


def load_adapter(name: str) -> None:
    """Import an optional adapter module so that it registers itself."""
    module = OPTIONAL_ADAPTERS.get(name)
    if module is None:
        raise KeyError(f"unknown optional adapter {name!r}; known: {sorted(OPTIONAL_ADAPTERS)}")
    importlib.import_module(module)


__all__ = ["OPTIONAL_ADAPTERS", "_deterministic_env", "_scene_replay", "load_adapter"]
