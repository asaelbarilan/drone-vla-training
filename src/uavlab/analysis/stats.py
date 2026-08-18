"""Paired statistics.

Architectures are compared *paired by seed*, because the same seed means the
same scene, the same obstacle layout and the same target placement.  Comparing
unpaired means across randomly generated scenes throws away most of the
statistical power and invites reading scene difficulty as an architecture
effect.

Bootstrap rather than a t-test: success is binary, latencies are skewed, and
episode counts are small.  No distributional assumption is needed and none is
made.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import mean


@dataclass(slots=True)
class PairedResult:
    """One paired contrast between two architectures on one metric."""

    metric: str
    baseline_id: str
    variant_id: str
    n_pairs: int
    baseline_mean: float
    variant_mean: float
    delta: float
    ci_low: float
    ci_high: float
    p_value: float

    @property
    def significant(self) -> bool:
        """Whether the confidence interval excludes zero."""
        return (self.ci_low > 0.0) or (self.ci_high < 0.0)

    def describe(self) -> str:
        direction = "higher" if self.delta > 0 else "lower"
        verdict = "" if self.significant else " (not distinguishable from zero)"
        return (
            f"{self.metric}: {self.variant_id} is {abs(self.delta):.3f} {direction} than "
            f"{self.baseline_id} "
            f"[95% CI {self.ci_low:+.3f}, {self.ci_high:+.3f}], n={self.n_pairs}{verdict}"
        )


def paired_bootstrap(
    baseline: dict[int, float],
    variant: dict[int, float],
    *,
    metric: str,
    baseline_id: str,
    variant_id: str,
    iterations: int = 10_000,
    seed: int = 0,
) -> PairedResult:
    """Bootstrap the mean paired difference ``variant - baseline`` over seeds."""
    shared = sorted(set(baseline) & set(variant))
    if not shared:
        raise ValueError(
            f"no shared seeds between {baseline_id} and {variant_id}; a paired "
            "comparison needs both architectures run on the same scenes"
        )
    diffs = [variant[s] - baseline[s] for s in shared]
    observed = mean(diffs)

    rng = random.Random(seed)
    n = len(diffs)
    resampled: list[float] = []
    for _ in range(iterations):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        resampled.append(mean(sample))
    resampled.sort()

    lo = resampled[int(0.025 * (iterations - 1))]
    hi = resampled[int(0.975 * (iterations - 1))]

    # Two-sided sign-flip test: how often does a random re-signing of the paired
    # differences produce an effect at least as large as the observed one?
    extreme = 0
    for _ in range(iterations):
        flipped = mean(d if rng.random() < 0.5 else -d for d in diffs)
        if abs(flipped) >= abs(observed):
            extreme += 1
    p_value = (extreme + 1) / (iterations + 1)

    return PairedResult(
        metric=metric,
        baseline_id=baseline_id,
        variant_id=variant_id,
        n_pairs=n,
        baseline_mean=mean(baseline[s] for s in shared),
        variant_mean=mean(variant[s] for s in shared),
        delta=observed,
        ci_low=lo,
        ci_high=hi,
        p_value=p_value,
    )


def bootstrap_ci(
    values: list[float], *, iterations: int = 10_000, seed: int = 0
) -> tuple[float, float, float]:
    """Mean and 95% CI for a single sample."""
    if not values:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    resampled = sorted(
        mean(values[rng.randrange(n)] for _ in range(n)) for _ in range(iterations)
    )
    return (
        mean(values),
        resampled[int(0.025 * (iterations - 1))],
        resampled[int(0.975 * (iterations - 1))],
    )
