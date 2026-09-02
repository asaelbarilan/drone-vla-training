"""Plugin registry: the indirection that makes an architecture a YAML name.

Configs refer to components by ``category`` + ``name``.  Nothing in the runtime
imports a concrete plugin class, so swapping C2 for C7 really is a config edit
and not an import change.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

CATEGORIES: tuple[str, ...] = (
    "environment",
    "perception",
    "memory",
    "policy",
    "monitor",
    "admission",
    "recovery",
    "verifier",
    "planner",
    "shield",
    "controller",
    "inference",
    "metrics",
)

T = TypeVar("T")

OPTIONAL_PLUGINS: dict[tuple[str, str], str] = {
    ("inference", "ollama"): "uavlab.plugins.inference.ollama",
    ("inference", "role_router"): "uavlab.plugins.inference.role_router",
    ("inference", "aerovla_hf"): "uavlab.plugins.inference.aerovla_hf",
    ("policy", "vlm_point_waypoint"): "uavlab.plugins.reasoning.vlm",
    ("policy", "spf_waypoint"): "uavlab.plugins.reasoning.spf",
    ("policy", "learned_visuomotor"): "uavlab.plugins.reasoning.learned",
    ("policy", "aerialclaw_agent"): "uavlab.plugins.reasoning.aerialclaw",
    ("policy", "aerovla"): "uavlab.plugins.reasoning.aerovla",
    ("policy", "onfly_decision"): "uavlab.plugins.reasoning.onfly",
    ("memory", "onfly_hybrid_memory"): "uavlab.plugins.reasoning.onfly",
    ("memory", "onfly_sliding_memory"): "uavlab.plugins.reasoning.onfly",
    ("monitor", "onfly_monitor"): "uavlab.plugins.reasoning.onfly",
    ("admission", "pmr_cvi"): "uavlab.plugins.admission.pmr",
    ("recovery", "pmr_recovery_reasoner"): "uavlab.plugins.recovery.pmr",
    ("verifier", "onfly_semantic_geometric"): "uavlab.plugins.reasoning.onfly",
}
"""Plugins imported on first use rather than at package import.

These reach outside the process, or pull in a heavy dependency: an HTTP client
for a local model server, the policy that drives it, and the trained policy that
imports torch. Importing them eagerly would mean ``import uavlab``
pulls in networking machinery, which breaks the property the whole test suite
depends on: that the core runtime and the core tests need nothing but pydantic,
pyyaml and numpy. Same treatment as the PX4 and AirSim adapters, for the same
reason.
"""


class PluginRegistry:
    """A flat ``(category, name) -> factory`` table."""

    def __init__(self) -> None:
        self._factories: dict[tuple[str, str], Callable[..., Any]] = {}

    def register(self, category: str, name: str) -> Callable[[type[T]], type[T]]:
        if category not in CATEGORIES:
            raise ValueError(f"unknown plugin category {category!r}; expected one of {CATEGORIES}")

        def decorator(cls: type[T]) -> type[T]:
            key = (category, name)
            if key in self._factories:
                raise ValueError(f"plugin {category}/{name} is already registered")
            self._factories[key] = cls
            return cls

        return decorator

    def build(self, category: str, name: str, params: dict[str, Any] | None = None) -> Any:
        key = (category, name)
        factory = self._factories.get(key)
        if factory is None and key in OPTIONAL_PLUGINS:
            # Lazily importable plugin: bring it in on first use.
            import importlib

            importlib.import_module(OPTIONAL_PLUGINS[key])
            factory = self._factories.get(key)
        if factory is None:
            available = ", ".join(sorted(n for c, n in self._factories if c == category)) or "none"
            raise KeyError(
                f"no plugin registered as {category}/{name}. Available in {category}: {available}"
            )
        try:
            return factory(**(params or {}))
        except TypeError as exc:
            raise TypeError(f"cannot construct {category}/{name} with {params!r}: {exc}") from exc

    def names(self, category: str) -> tuple[str, ...]:
        """Every plugin that can be built, including the lazily importable ones."""
        registered = {n for c, n in self._factories if c == category}
        optional = {n for c, n in OPTIONAL_PLUGINS if c == category}
        return tuple(sorted(registered | optional))

    def has(self, category: str, name: str) -> bool:
        """Whether ``build`` would succeed.

        Includes lazily importable plugins. Reporting them as absent merely
        because nothing had imported them yet would make ``validate-config``
        reject a configuration that runs perfectly well.
        """
        key = (category, name)
        return key in self._factories or key in OPTIONAL_PLUGINS

    def __len__(self) -> int:
        return len(self._factories)


REGISTRY = PluginRegistry()


def register(category: str, name: str) -> Callable[[type[T]], type[T]]:
    """Module-level decorator bound to the process-wide registry."""
    return REGISTRY.register(category, name)
