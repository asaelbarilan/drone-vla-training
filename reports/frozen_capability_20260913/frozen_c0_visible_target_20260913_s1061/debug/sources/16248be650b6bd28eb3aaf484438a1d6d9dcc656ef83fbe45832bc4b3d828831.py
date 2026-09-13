"""Simulated inference backend.

Compute cost is the currency of half this study, so it is modelled explicitly
rather than left to whatever hardware happens to run the sweep.  A call charges
its latency against the *simulation* clock, which means a 2.5 s reasoner really
does leave 2.5 s of flight to whatever else is scheduled — deterministically,
and without a GPU.

Latencies are stated per architectural role, so the numbers can be set from the
published figures for whichever system a configuration is modelled on and then
held fixed across the architectures being compared.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from uavlab.contracts import MissionSpec, s_to_ns
from uavlab.contracts.events import EventType
from uavlab.core.registry import register
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import InferenceRequest, InferenceResult

DEFAULT_LATENCY_S = {
    "perception": 0.02,
    "policy": 0.30,
    "monitor": 1.20,
    "reasoner": 2.50,
    "verifier": 0.01,
}
DEFAULT_TOKENS = {"perception": 0, "policy": 160, "monitor": 300, "reasoner": 800, "verifier": 0}


@register("inference", "simulated")
class SimulatedInference:
    """Charges configured latency and token cost to the shared clock."""

    def __init__(self, **params: Any) -> None:
        self.latency_s = {**DEFAULT_LATENCY_S, **dict(params.get("latency_s", {}))}
        self.tokens = {**DEFAULT_TOKENS, **dict(params.get("tokens_per_call", {}))}
        self.jitter_frac = float(params.get("jitter_frac", 0.0))
        self.model_id = str(params.get("model_id", "sim-model-v1"))
        self._services: RuntimeServices | None = None
        self._rng = np.random.default_rng(0)
        self._calls: dict[str, int] = {}
        self._tokens_out: dict[str, int] = {}
        self._latency_ns: dict[str, int] = {}

    @property
    def name(self) -> str:
        return "simulated"

    def bind_runtime(self, services: RuntimeServices) -> None:
        self._services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._rng = np.random.default_rng(seed + 977)
        self._calls = {}
        self._tokens_out = {}
        self._latency_ns = {}

    def _sample_latency_ns(self, role: str) -> int:
        base = float(self.latency_s.get(role, 0.05))
        if self.jitter_frac > 0.0:
            factor = float(self._rng.normal(1.0, self.jitter_frac))
            base *= max(0.1, factor)
        return s_to_ns(base)

    async def invoke(self, request: InferenceRequest) -> InferenceResult:
        latency_ns = self._sample_latency_ns(request.role)
        cache_hit = False

        if self._services is not None and self._services.feature_cache.enabled and request.image_count:
            key = self._services.feature_cache.key(
                request.model_id, "shared_vit", request.observation_seq, request.prompt_hash[:8]
            )
            if self._services.feature_cache.get(key) is not None:
                cache_hit = True
                latency_ns = int(latency_ns * 0.55)
            else:
                self._services.feature_cache.put(key, object())

        if self._services is not None and latency_ns > 0:
            await self._services.clock.sleep_ns(latency_ns)

        out_tokens = int(self.tokens.get(request.role, 0))
        self._calls[request.role] = self._calls.get(request.role, 0) + 1
        self._tokens_out[request.role] = self._tokens_out.get(request.role, 0) + out_tokens
        self._latency_ns[request.role] = self._latency_ns.get(request.role, 0) + latency_ns

        if self._services is not None:
            self._services.log.emit(
                f"inference/{request.role}",
                EventType.INFERENCE_CALL,
                self._services.clock.now_ns(),
                self._services.clock.wall_ns(),
                payload={
                    "role": request.role,
                    "model_id": request.model_id,
                    "latency_s": latency_ns / 1e9,
                    "output_tokens": out_tokens,
                    "input_tokens": request.input_tokens,
                    "cache_hit": cache_hit,
                },
            )
        return InferenceResult(
            payload=None, output_tokens=out_tokens, latency_ns=latency_ns, cache_hit=cache_hit
        )

    def stats(self) -> dict[str, float]:
        out: dict[str, float] = {}
        total_calls = 0
        total_tokens = 0
        for role, calls in self._calls.items():
            out[f"inference_calls_{role}"] = float(calls)
            out[f"inference_tokens_{role}"] = float(self._tokens_out.get(role, 0))
            out[f"inference_latency_s_{role}"] = self._latency_ns.get(role, 0) / 1e9
            total_calls += calls
            total_tokens += self._tokens_out.get(role, 0)
        out["inference_calls_total"] = float(total_calls)
        out["inference_tokens_total"] = float(total_tokens)
        # Reasoner calls are reported separately: "how often was expensive
        # reasoning admitted" is the headline number for the PMR-style family.
        out["reasoner_calls"] = float(self._calls.get("reasoner", 0))
        return out


@register("inference", "free")
class FreeInference(SimulatedInference):
    """Zero-latency backend for unit tests and the oracle control ceiling."""

    def __init__(self, **params: Any) -> None:
        params.setdefault("latency_s", {k: 0.0 for k in DEFAULT_LATENCY_S})
        params.setdefault("tokens_per_call", {k: 0 for k in DEFAULT_TOKENS})
        super().__init__(**params)

    @property
    def name(self) -> str:
        return "free"
