from __future__ import annotations

import asyncio
import json

from uavlab.core.config import ExperimentConfig
from uavlab.experiments.sweep import run_sweep


def test_kept_sweep_logs_include_the_full_episode_result(tmp_path):
    experiment = ExperimentConfig(
        id="result-persistence",
        architectures=("c0",),
        environments=("grid_nav",),
        seeds=(2,),
    )

    outcome = asyncio.run(
        run_sweep(experiment, out_dir=tmp_path, keep_episode_logs=True, progress=False)
    )

    path = tmp_path / "episodes" / "c0__grid_nav__s2" / "result.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["seed"] == 2
    assert saved["metrics"] == outcome.results[0].model_dump(mode="json")["metrics"]
