"""Sweep execution: architecture x environment x seed.

The staging matters and is not incidental.  Screening runs cheaply and broadly
first; only the two or three architectures that survive on the Pareto frontier
are worth promoting to a heavier simulator, and only after that is it worth
investigating shared encoders, KV caching, quantisation or model scaling. Doing
deployment optimisation earlier would confound functional architecture with
implementation efficiency, which is the exact mistake this testbed exists to
avoid.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from uavlab.analysis.report import CellSummary, compare, summarise, write_report
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec, ExperimentConfig
from uavlab.core.orchestrator import Orchestrator
from uavlab.core.results import EpisodeResult
from uavlab.experiments.manifest import build_manifest, write_manifest


@dataclass(slots=True)
class SweepOutcome:
    experiment_id: str
    results: list[EpisodeResult]
    cells: dict[tuple[str, str], CellSummary]
    comparisons: list[dict[str, object]]
    out_dir: Path
    failures: list[tuple[str, str, int, str]]
    """``(architecture, environment, seed, error)`` for episodes that crashed."""


async def run_sweep(
    experiment: ExperimentConfig,
    *,
    config_root: Path | None = None,
    out_dir: Path | None = None,
    keep_episode_logs: bool = False,
    progress: bool = True,
) -> SweepOutcome:
    """Run every cell of an experiment and write the report."""
    out_dir = out_dir or Path("runs") / experiment.id
    out_dir.mkdir(parents=True, exist_ok=True)

    architectures = {a: load_architecture(a, config_root) for a in experiment.architectures}
    environments = {e: load_environment(e, config_root) for e in experiment.environments}

    for arch_name, arch in architectures.items():
        for env_name, env in environments.items():
            manifest = build_manifest(
                arch,
                env,
                seeds=list(experiment.seeds),
                extra={"experiment_id": experiment.id, "stage": experiment.stage},
            )
            write_manifest(manifest, out_dir / "manifests" / f"{arch_name}__{env_name}")

    results: list[EpisodeResult] = []
    failures: list[tuple[str, str, int, str]] = []
    cells = experiment.cells()

    for index, (arch_name, env_name, seed) in enumerate(cells, start=1):
        arch = architectures[arch_name]
        env = environments[env_name]
        episode_id = f"{arch.id}__{env.id}__s{seed}"
        episode_dir = (out_dir / "episodes" / episode_id) if keep_episode_logs else None

        orchestrator = Orchestrator(
            arch, env, EpisodeSpec(episode_id=episode_id, seed=seed), out_dir=episode_dir
        )
        result = await orchestrator.run()
        results.append(result)
        if episode_dir is not None:
            (episode_dir / "result.json").write_text(
                json.dumps(result.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
        if result.error:
            failures.append((arch.id, env.id, seed, result.error))

        if progress:
            print(
                f"[{index:>4}/{len(cells)}] {arch.id:<5} {env.id:<18} seed={seed:<6} "
                f"success={str(result.success):<5} {result.termination_reason.value}",
                flush=True,
            )

    summaries = summarise(results)
    comparisons = compare(summaries, [tuple(p) for p in experiment.compare])
    write_report(summaries, comparisons, out_dir)

    return SweepOutcome(
        experiment_id=experiment.id,
        results=results,
        cells=summaries,
        comparisons=comparisons,
        out_dir=out_dir,
        failures=failures,
    )


def run_sweep_sync(experiment: ExperimentConfig, **kwargs) -> SweepOutcome:
    return asyncio.run(run_sweep(experiment, **kwargs))
