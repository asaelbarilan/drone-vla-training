"""uavlab — a modular testbed for searching single-UAV autonomy architectures.

The organising principle of this package is one sentence:

    architectures are configuration; simulators, models, controllers and
    datasets are adapters.

So the runtime is a thin typed kernel — contracts, a scheduler, a decision
router, a clock, an event log — surrounded by plugin interfaces.  Swapping a
waypoint architecture for a direct-VLA one is a YAML edit, and running the same
architecture against a different simulator is an adapter swap.  Neither is a
code change.

Importing this package registers the built-in plugins and the deterministic
environment, so :func:`uavlab.core.orchestrator.run_episode` works immediately.
"""

from uavlab import adapters as _adapters  # noqa: F401  (registers grid3d)
from uavlab import plugins as _plugins  # noqa: F401  (registers built-ins)
from uavlab.core.compose import (
    load_architecture,
    load_environment,
    load_experiment,
)
from uavlab.core.config import ArchitectureConfig, EnvironmentConfig, EpisodeSpec
from uavlab.core.orchestrator import Orchestrator, run_episode
from uavlab.core.registry import REGISTRY
from uavlab.core.results import EpisodeResult

__version__ = "0.1.0"

__all__ = [
    "REGISTRY",
    "ArchitectureConfig",
    "EnvironmentConfig",
    "EpisodeResult",
    "EpisodeSpec",
    "Orchestrator",
    "load_architecture",
    "load_environment",
    "load_experiment",
    "run_episode",
]
