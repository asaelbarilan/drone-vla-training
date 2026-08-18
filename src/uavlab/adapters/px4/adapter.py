"""PX4 SITL + Gazebo adapter — the dynamics and control realism slot.

Not implemented yet.  PX4/Gazebo is the right place to validate dynamics,
control authority and recovery behaviour, and the wrong place to run a first
architecture sweep: pushing thousands of cheap screening episodes through SITL
would make the screen slow for no scientific gain.

The intended flow is that the *same* architecture YAML that ran against the
deterministic environment runs here unchanged, with only the environment config
swapped.  If that ever requires editing an architecture file, the adapter
boundary has leaked and the leak is the bug.

Implementation notes for later:

* Command path via MAVSDK offboard velocity setpoints or the PX4 ROS 2 control
  interface; either is an adapter detail and neither belongs in a contract.
* Convert ENU to NED exactly once, at this boundary, through
  :mod:`uavlab.core.frames`. Never let a plugin see NED.
* Flight-stack message types must not appear in any semantic model API.
* Simulation time comes from the simulator, not from :class:`SimClock`; the
  clock becomes an observer rather than a driver, and ``decision_age`` is then
  measured against real simulator timestamps.
"""

from __future__ import annotations

from typing import Any

from uavlab.contracts import ControlCommand, MissionSpec, ObservationPacket
from uavlab.contracts.env_status import EnvironmentStatus
from uavlab.core.registry import register

INSTALL_HINT = (
    "PX4 SITL + Gazebo is not available in this environment. See docs/SIMULATORS.md. "
    "Core tests and architecture screening never require it."
)


@register("environment", "px4_sitl")
class PX4SitlAdapter:
    """Placeholder that fails loudly at construction rather than silently degrading."""

    def __init__(self, **params: Any) -> None:
        raise NotImplementedError(INSTALL_HINT)

    @property
    def name(self) -> str:  # pragma: no cover
        return "px4_sitl"

    async def reset(self, mission: MissionSpec, seed: int) -> ObservationPacket:  # pragma: no cover
        raise NotImplementedError(INSTALL_HINT)

    async def observe(self) -> ObservationPacket:  # pragma: no cover
        raise NotImplementedError(INSTALL_HINT)

    async def step(self, command: ControlCommand, dt_ns: int) -> None:  # pragma: no cover
        raise NotImplementedError(INSTALL_HINT)

    def status(self) -> EnvironmentStatus:  # pragma: no cover
        raise NotImplementedError(INSTALL_HINT)

    async def close(self) -> None:  # pragma: no cover
        return None
