"""Safety accounting, comparable across architectures.

The shield is an independent component precisely so that C7 vs C8 (same VLA,
shield off/on) isolates "is this stack's safety weakness separable from its
control competence?" instead of confounding it with model quality.
"""

from __future__ import annotations

from pydantic import Field

from uavlab.contracts.common import SafetyVerdict, StrictModel


class SafetyDecision(StrictModel):
    """What the shield did, why, and at what cost."""

    verdict: SafetyVerdict
    reason: str
    risk: float = 0.0
    """0 = nominal, 1 = imminent violation."""
    source_decision_id: str | None = None
    modified: bool = False
    """True when the executed command differs from the proposal."""
    intervention_magnitude: float = 0.0
    """How far the shield had to move the command; a shield that constantly
    rewrites actions is not "safe", it is driving."""
    t_sim_ns: int = 0
    details: dict[str, float] = Field(default_factory=dict)
