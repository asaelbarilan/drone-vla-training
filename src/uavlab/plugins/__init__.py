"""Plugin implementations.

Importing this package registers every built-in plugin.  The registry is the
only way the runtime reaches an implementation, so a config can name
``mock_vla`` or ``vlm_waypoint`` without any part of the core importing either.

Everything here is a *fake or classical* component: scripted policies, a
simulated inference backend, a fixed local planner, a bounds verifier, a
collision shield.

Real model adapters (the Ollama backend, the VLM policy) are deliberately *not*
imported here. They are listed in ``uavlab.core.registry.OPTIONAL_PLUGINS`` and
load on first use, so that ``import uavlab`` never pulls in networking. They are
still selected the same way — by name, from YAML.
"""

from uavlab.plugins.control import mock as _control_mock
from uavlab.plugins.inference import simulated as _inference_simulated
from uavlab.plugins.memory import stores as _memory_stores
from uavlab.plugins.monitoring import progress as _monitoring_progress
from uavlab.plugins.perception import identity as _perception_identity
from uavlab.plugins.planning import local as _planning_local
from uavlab.plugins.planning import super as _planning_super
from uavlab.plugins.reasoning import policies as _reasoning_policies
from uavlab.plugins.recovery import reasoner as _recovery_reasoner
from uavlab.plugins.shield import collision as _shield_collision
from uavlab.plugins.verifier import bounds as _verifier_bounds

__all__ = [
    "_control_mock",
    "_inference_simulated",
    "_memory_stores",
    "_monitoring_progress",
    "_perception_identity",
    "_planning_local",
    "_planning_super",
    "_reasoning_policies",
    "_recovery_reasoner",
    "_shield_collision",
    "_verifier_bounds",
]
