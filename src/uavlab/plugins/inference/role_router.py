"""Role-indexed composition of inference backends.

An architecture has one shared inference service, but a paper implementation
may use different foundation models for different semantic roles. PMR is the
motivating case: OnFly's local policy is visual while the admitted recovery
agent is a text reasoner. Both remain behind the testbed's accounting boundary.
"""

from __future__ import annotations

from typing import Any

from uavlab.contracts import MissionSpec
from uavlab.core.registry import REGISTRY, register
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import InferenceRequest, InferenceResult


@register("inference", "role_router")
class RoleRoutedInference:
    """Dispatch each request role to a declaratively configured backend."""

    def __init__(self, **params: Any) -> None:
        raw_routes = params.get("routes")
        if not isinstance(raw_routes, dict) or not raw_routes:
            raise ValueError("role_router requires a non-empty routes mapping")
        self._routes: dict[str, object] = {}
        for role, raw_spec in raw_routes.items():
            if not isinstance(role, str) or not role:
                raise ValueError("role_router route names must be non-empty strings")
            if not isinstance(raw_spec, dict):
                raise ValueError(f"role_router route {role!r} must be a component mapping")
            name = raw_spec.get("name")
            route_params = raw_spec.get("params", {})
            if not isinstance(name, str) or not name:
                raise ValueError(f"role_router route {role!r} requires backend name")
            if name == "role_router":
                raise ValueError("role_router cannot recursively route to itself")
            if not isinstance(route_params, dict):
                raise ValueError(f"role_router route {role!r} params must be a mapping")
            self._routes[role] = REGISTRY.build("inference", name, route_params)
        self.default_role = str(params.get("default_role", "policy"))
        if self.default_role not in self._routes:
            raise ValueError(
                f"role_router default_role {self.default_role!r} has no configured route"
            )
        # Compatibility for policies that inspect the shared backend's model.
        self.model_id = self.model_for_role(self.default_role)

    @property
    def name(self) -> str:
        return "role_router"

    def backend_for_role(self, role: str) -> object:
        try:
            return self._routes[role]
        except KeyError as exc:
            raise RuntimeError(
                f"no inference backend is configured for semantic role {role!r}"
            ) from exc

    def model_for_role(self, role: str) -> str:
        backend = self.backend_for_role(role)
        model_id = getattr(backend, "model_id", None)
        if not isinstance(model_id, str) or not model_id:
            raise RuntimeError(f"inference route {role!r} does not declare a model_id")
        return model_id

    def backend_name_for_role(self, role: str) -> str:
        return str(getattr(self.backend_for_role(role), "name", ""))

    def bind_runtime(self, services: RuntimeServices) -> None:
        for backend in self._routes.values():
            bind(backend, services)

    def reset(self, mission: MissionSpec, seed: int) -> None:
        for backend in self._routes.values():
            reset = getattr(backend, "reset", None)
            if callable(reset):
                reset(mission, seed)

    async def invoke(self, request: InferenceRequest) -> InferenceResult:
        backend = self.backend_for_role(request.role)
        routed_model = self.model_for_role(request.role)
        if request.model_id != routed_model:
            raise RuntimeError(
                f"{request.role} requests model {request.model_id!r}, but its route serves "
                f"{routed_model!r}"
            )
        return await backend.invoke(request)  # type: ignore[attr-defined,no-any-return]

    def available(self) -> bool:
        for backend in self._routes.values():
            probe = getattr(backend, "available", None)
            if callable(probe) and not probe():
                return False
        return True

    def close(self) -> None:
        for backend in self._routes.values():
            close = getattr(backend, "close", None)
            if callable(close):
                close()

    def stats(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for backend in self._routes.values():
            stats = getattr(backend, "stats", None)
            if not callable(stats):
                continue
            for key, value in stats().items():
                totals[key] = totals.get(key, 0.0) + float(value)
        return totals
