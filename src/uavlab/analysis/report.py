"""Aggregation and reporting.

Aggregation happens per (architecture, environment) cell and never pools across
task regimes.  Pooling would be the single easiest way to manufacture a false
conclusion here: the whole premise of the study is that different regimes favour
different architectures, so a pooled mean is an average over the very thing
being measured.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from uavlab.analysis.metrics import percentile
from uavlab.analysis.pareto import DEFAULT_OBJECTIVES, pareto_front
from uavlab.analysis.stats import paired_bootstrap
from uavlab.core.results import EpisodeResult

HEADLINE_METRICS: tuple[str, ...] = (
    "success_rate",
    "collision_rate",
    "correct_terminal_stop",
    "recovery_success",
    "false_target_commitment",
    "path_efficiency",
    "flight_time_s",
    "semantic_latency_median_s",
    "semantic_latency_p95_s",
    "actual_control_hz",
    "decision_age_median_s",
    "stale_action_rate",
    "executable_plan_rate",
    "safety_intervention_rate",
    "reasoner_calls",
    "inference_tokens_total",
    "peak_rss_mb",
)


@dataclass(slots=True)
class CellSummary:
    """Aggregated results for one architecture in one environment."""

    architecture_id: str
    environment_id: str
    task_family: str
    n_episodes: int
    metrics: dict[str, float]
    per_seed: dict[str, dict[int, float]]
    is_reference: bool = False
    """A control ceiling rather than a competitor.

    The oracle sees ground truth, so it dominates every real architecture by
    construction. Leaving it on the Pareto frontier would make the frontier say
    only "perfect semantics wins", which is not a finding.
    """

    def get(self, metric: str, default: float = 0.0) -> float:
        return self.metrics.get(metric, default)


def summarise(results: list[EpisodeResult]) -> dict[tuple[str, str], CellSummary]:
    """Group episodes into (architecture, environment) cells."""
    cells: dict[tuple[str, str], list[EpisodeResult]] = {}
    for r in results:
        cells.setdefault((r.architecture_id, r.environment_id), []).append(r)

    out: dict[tuple[str, str], CellSummary] = {}
    for key, group in cells.items():
        metrics: dict[str, float] = {}
        per_seed: dict[str, dict[int, float]] = {}

        successes = [1.0 if r.success else 0.0 for r in group]
        metrics["success_rate"] = mean(successes)
        per_seed["success_rate"] = {r.seed: (1.0 if r.success else 0.0) for r in group}

        keys = sorted({k for r in group for k in r.metrics})
        for metric in keys:
            values = [r.metrics[metric] for r in group if metric in r.metrics]
            if not values:
                continue
            metrics[metric] = mean(values)
            metrics[f"{metric}__p95"] = percentile(values, 95.0)
            per_seed[metric] = {r.seed: r.metrics[metric] for r in group if metric in r.metrics}

        # Recovery is scored only on episodes where recovery was actually
        # attempted; averaging over episodes that never needed it would make the
        # rate a function of scenario mix rather than of recovery quality.
        attempted = [r for r in group if r.metrics.get("recovery_attempted", 0.0) > 0.0]
        metrics["recovery_success"] = (
            mean(r.metrics.get("recovery_success", 0.0) for r in attempted) if attempted else 0.0
        )
        metrics["recovery_attempted_episodes"] = float(len(attempted))

        out[key] = CellSummary(
            architecture_id=key[0],
            environment_id=key[1],
            task_family=group[0].task_family.value,
            n_episodes=len(group),
            metrics=metrics,
            per_seed=per_seed,
            is_reference=any(r.used_privileged_observations for r in group),
        )
    return out


def compare(
    cells: dict[tuple[str, str], CellSummary],
    pairs: list[tuple[str, str]],
    metrics: tuple[str, ...] = ("success_rate", "collision_rate", "correct_terminal_stop"),
    iterations: int = 4000,
) -> list[dict[str, object]]:
    """Run the declared paired contrasts, per environment."""
    out: list[dict[str, object]] = []
    environments = sorted({env for _, env in cells})
    for baseline_id, variant_id in pairs:
        for env in environments:
            base = cells.get((baseline_id, env))
            var = cells.get((variant_id, env))
            if base is None or var is None:
                continue
            for metric in metrics:
                if metric not in base.per_seed or metric not in var.per_seed:
                    continue
                try:
                    result = paired_bootstrap(
                        base.per_seed[metric],
                        var.per_seed[metric],
                        metric=metric,
                        baseline_id=baseline_id,
                        variant_id=variant_id,
                        iterations=iterations,
                    )
                except ValueError:
                    continue
                out.append(
                    {
                        "environment": env,
                        "metric": metric,
                        "baseline": baseline_id,
                        "variant": variant_id,
                        "baseline_mean": result.baseline_mean,
                        "variant_mean": result.variant_mean,
                        "delta": result.delta,
                        "ci_low": result.ci_low,
                        "ci_high": result.ci_high,
                        "p_value": result.p_value,
                        "significant": result.significant,
                        "n_pairs": result.n_pairs,
                        "description": result.describe(),
                    }
                )
    return out


def render_table(cells: dict[tuple[str, str], CellSummary]) -> str:
    """A per-environment text table. One block per regime, never pooled."""
    lines: list[str] = []
    for env in sorted({e for _, e in cells}):
        block = {k: v for k, v in cells.items() if k[1] == env}
        if not block:
            continue
        family = next(iter(block.values())).task_family
        lines.append(f"\n=== {env}  ({family}) ===")
        header = f"{'arch':<6}{'n':>4}{'SR':>7}{'coll':>7}{'stop':>7}{'eff':>7}{'p95_lat':>9}{'age':>7}{'reas':>7}"
        lines.append(header)
        lines.append("-" * len(header))
        for (arch_id, _), cell in sorted(block.items()):
            lines.append(
                f"{arch_id:<6}{cell.n_episodes:>4}"
                f"{cell.get('success_rate'):>7.2f}"
                f"{cell.get('collision_rate'):>7.2f}"
                f"{cell.get('correct_terminal_stop'):>7.2f}"
                f"{cell.get('path_efficiency'):>7.2f}"
                f"{cell.get('semantic_latency_p95_s'):>9.2f}"
                f"{cell.get('decision_age_median_s'):>7.2f}"
                f"{cell.get('reasoner_calls'):>7.1f}"
            )
    return "\n".join(lines)


def render_pareto(cells: dict[tuple[str, str], CellSummary]) -> str:
    lines = ["\n=== Pareto frontier (per environment) ==="]
    for env in sorted({e for _, e in cells}):
        block = {arch: cell for (arch, e), cell in cells.items() if e == env}
        references = sorted(arch for arch, cell in block.items() if cell.is_reference)
        summaries = {
            arch: dict(cell.metrics) for arch, cell in block.items() if not cell.is_reference
        }
        if not summaries:
            continue
        points = pareto_front(summaries, DEFAULT_OBJECTIVES)
        front = [p.architecture_id for p in points if p.on_front]
        lines.append(f"{env}: {', '.join(front) if front else '(none)'}")
        for p in points:
            if not p.on_front:
                lines.append(f"    {p.architecture_id} dominated by {', '.join(p.dominated_by)}")
        for arch in references:
            cell = block[arch]
            lines.append(
                f"    [reference, excluded from the frontier] {arch}: "
                f"SR={cell.get('success_rate'):.2f} coll={cell.get('collision_rate'):.2f} "
                "- sees ground truth, so it is a ceiling to measure against, not a competitor"
            )
    lines.append(
        "\nNo single score is computed. An architecture on the frontier is not "
        "'best'; it is un-dominated given these objectives."
    )
    return "\n".join(lines)


def write_report(
    cells: dict[tuple[str, str], CellSummary],
    comparisons: list[dict[str, object]],
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "cells": [
            {
                "architecture": cell.architecture_id,
                "environment": cell.environment_id,
                "task_family": cell.task_family,
                "n_episodes": cell.n_episodes,
                "metrics": {k: cell.metrics.get(k) for k in HEADLINE_METRICS if k in cell.metrics},
            }
            for cell in cells.values()
        ],
        "comparisons": comparisons,
    }
    path = out_dir / "report.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "report.txt").write_text(
        render_table(cells) + "\n" + render_pareto(cells) + "\n", encoding="utf-8"
    )
    return path
