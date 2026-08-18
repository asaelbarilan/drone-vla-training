"""Project AirSim adapter — the vision-rich environment slot.

Not implemented yet, and deliberately so.  The environment adapter priority for
this testbed is:

1. the deterministic in-process environment (fast architecture screening),
2. PX4 SITL + Gazebo (dynamics, control and recovery realism),
3. Project AirSim (vision-rich scenes),
4. dataset replay,
5. an optional high-throughput backend.

Screening runs in the thousands of episodes, so forcing every architecture sweep
through a photorealistic simulator would make cheap screening pointlessly slow.
Architectures earn promotion to this adapter by surviving the deterministic one.

Note on which AirSim: the legacy ``microsoft/AirSim`` repository is archived and
is *not* the target here.  Project AirSim is the maintained successor, and even
it is only ever an adapter — never a dependency of the core runtime, and never
importable from the core tests.

Contract for whoever implements this: produce a valid
:class:`~uavlab.contracts.observation.ObservationPacket` and consume the
canonical :class:`~uavlab.contracts.motion.ControlCommand`.  Nothing else in the
testbed may change.  Populate ``rgb``/``depth`` with real frames and leave
``semantic_hits`` empty, so that a real perception plugin does the detection
work that the lightweight environment simulates.
"""

from __future__ import annotations

from typing import Any

from uavlab.contracts import ControlCommand, MissionSpec, ObservationPacket
from uavlab.contracts.env_status import EnvironmentStatus
from uavlab.core.registry import register

INSTALL_HINT = (
    "Project AirSim is not installed. Install it separately (see docs/SIMULATORS.md), "
    "then run with --env configs/environments/airsim_city.yaml. "
    "The deterministic environment (adapter: grid3d) needs no installation and is the "
    "correct place to screen architectures first."
)


@register("environment", "project_airsim")
class ProjectAirSimAdapter:
    """Placeholder that fails loudly at construction rather than silently degrading."""

    def __init__(self, **params: Any) -> None:
        raise NotImplementedError(INSTALL_HINT)

    @property
    def name(self) -> str:  # pragma: no cover - unreachable until implemented
        return "project_airsim"

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
