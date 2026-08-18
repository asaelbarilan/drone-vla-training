"""Pareto analysis over the capability/cost surface.

There is deliberately no global architecture score.  The scientific object of
this study is not "the universally best UAV architecture" but

    A* = f(task regime, semantic uncertainty, flight dynamics,
           compute budget, latency budget)

and a single scalar would erase exactly the trade-off that formulation is about.
So the analysis reports a frontier: the set of architectures that nothing else
dominates on every axis at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Direction = Literal["max", "min"]

DEFAULT_OBJECTIVES: dict[str, Direction] = {
    "success_rate": "max",
    "collision_rate": "min",
    "correct_terminal_stop": "max",
    "semantic_latency_p95_s": "min",
    "decision_age_median_s": "min",
    "reasoner_calls": "min",
}
"""Capability up, cost down. Chosen to span both halves of the surface."""


@dataclass(slots=True)
class ParetoPoint:
    architecture_id: str
    values: dict[str, float]
    dominated_by: list[str]

    @property
    def on_front(self) -> bool:
        return not self.dominated_by


def dominates(
    a: dict[str, float], b: dict[str, float], objectives: dict[str, Direction]
) -> bool:
    """True when ``a`` is at least as good on every objective and better on one."""
    strictly_better = False
    for metric, direction in objectives.items():
        if metric not in a or metric not in b:
            continue
        av, bv = a[metric], b[metric]
        if direction == "max":
            if av < bv:
                return False
            if av > bv:
                strictly_better = True
        else:
            if av > bv:
                return False
            if av < bv:
                strictly_better = True
    return strictly_better


def pareto_front(
    summaries: dict[str, dict[str, float]],
    objectives: dict[str, Direction] | None = None,
) -> list[ParetoPoint]:
    """Compute the frontier, recording *who* dominates each dominated point."""
    objectives = objectives or DEFAULT_OBJECTIVES
    points: list[ParetoPoint] = []
    for arch_id, values in summaries.items():
        dominators = [
            other_id
            for other_id, other in summaries.items()
            if other_id != arch_id and dominates(other, values, objectives)
        ]
        points.append(ParetoPoint(arch_id, values, sorted(dominators)))
    points.sort(key=lambda p: (not p.on_front, p.architecture_id))
    return points


def front_ids(
    summaries: dict[str, dict[str, float]],
    objectives: dict[str, Direction] | None = None,
) -> list[str]:
    return [p.architecture_id for p in pareto_front(summaries, objectives) if p.on_front]
