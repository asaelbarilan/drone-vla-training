"""Typed boundary for selective reasoner admission.

Admission decides whether an expensive recovery query is worth issuing.  It
does not choose a recovery action and has no motion authority.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from uavlab.contracts.common import StrictModel


class AdmissionRuntime(StrictModel):
    """Runtime-owned state supplied to an admission policy."""

    t_sim_ns: int
    call_count: int = 0
    max_calls: int | None = None
    last_call_t_sim_ns: int | None = None
    cooldown_s: float = 0.0
    planner_failed: bool = False
    safety_interventions: int = 0


class AdmissionDecision(StrictModel):
    """Auditable decision from a selective-admission policy."""

    admit: bool
    score: float
    threshold: float
    hard_stuck: bool = False
    guards: dict[str, bool] = Field(default_factory=dict)
    feature_names: tuple[str, ...] = ()
    features: tuple[float, ...] = ()
    reason: str = ""

    @model_validator(mode="after")
    def _validate_shape(self) -> AdmissionDecision:
        if len(self.feature_names) != len(self.features):
            raise ValueError("admission feature names and values must have equal length")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"admission score must be in [0, 1], got {self.score}")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"admission threshold must be in [0, 1], got {self.threshold}")
        return self
