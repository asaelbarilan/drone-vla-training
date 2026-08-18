"""Runtime services handed to plugins after construction.

Plugins are built from YAML, so their constructors only receive declarative
parameters.  Everything that belongs to the *run* rather than to the
configuration — the simulation clock, the inference backend, the shared feature
cache, the event log — arrives afterwards through :meth:`bind_runtime`.

That split is what keeps a plugin from privately owning timing.  A policy
cannot start its own timer or its own thread; it can only charge simulated
compute against the one clock the whole episode shares.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache


@dataclass(slots=True)
class RuntimeServices:
    """Shared, per-episode runtime handles."""

    clock: SimClock
    log: EventLog
    feature_cache: FeatureCache
    inference: object | None = None
    """An :class:`~uavlab.interfaces.InferenceBackend`; typed loosely to avoid a cycle."""
    episode_id: str = ""
    seed: int = 0


@runtime_checkable
class RuntimeBound(Protocol):
    """Optional hook. Plugins that need runtime services implement it."""

    def bind_runtime(self, services: RuntimeServices) -> None: ...


def bind(component: object, services: RuntimeServices) -> None:
    """Bind if the component wants it; silently skip otherwise."""
    hook = getattr(component, "bind_runtime", None)
    if callable(hook):
        hook(services)
