"""Score one learned-policy checkpoint without changing the shipped configs.

This is intentionally a thin experiment driver.  It loads C7T and C8T, swaps
only the checkpoint path in memory, and runs paired local-simulator seeds.  The
result therefore measures the candidate network and the C7T/C8T shield contrast
without turning an unevaluated checkpoint into the repository default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections import Counter
from pathlib import Path

from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator


def _with_checkpoint(architecture_id: str, checkpoint: Path):
    arch = load_architecture(architecture_id)
    params = dict(arch.policy.params)
    params["checkpoint"] = str(checkpoint)
    policy = arch.policy.model_copy(update={"params": params})
    return arch.model_copy(update={"policy": policy})


async def _run(args: argparse.Namespace) -> dict:
    env = load_environment(args.env)
    rows: list[dict] = []
    summary: dict[str, dict] = {}

    for architecture_id in args.architectures:
        arch = _with_checkpoint(architecture_id, args.checkpoint)
        results = []
        for seed in args.seeds:
            result = await Orchestrator(
                arch,
                env,
                EpisodeSpec(episode_id=f"{architecture_id}_checkpoint_s{seed}", seed=seed),
            ).run()
            results.append(result)
            rows.append(
                {
                    "architecture": architecture_id,
                    "seed": seed,
                    "success": result.success,
                    "termination": result.termination_reason.value,
                    "reached_goal": result.metrics.get("reached_goal", 0.0),
                    "distance_to_goal_m": result.metrics.get("distance_to_goal_m", -1.0),
                    "path_length_m": result.metrics.get("path_length_m", -1.0),
                    "collisions": result.metrics.get("collisions", 0.0),
                }
            )
            if len(results) % 10 == 0:
                print(f"{architecture_id}: {len(results)}/{len(args.seeds)}", flush=True)

        summary[architecture_id] = {
            "episodes": len(results),
            "success_rate": sum(r.success for r in results) / len(results),
            "reached_goal_rate": sum(r.metrics.get("reached_goal", 0.0) for r in results)
            / len(results),
            "collision_rate": sum(r.metrics.get("collision_rate", 0.0) for r in results)
            / len(results),
            "median_final_distance_m": statistics.median(
                r.metrics.get("distance_to_goal_m", -1.0) for r in results
            ),
            "median_path_length_m": statistics.median(
                r.metrics.get("path_length_m", -1.0) for r in results
            ),
            "terminations": dict(Counter(r.termination_reason.value for r in results)),
        }

    return {
        "checkpoint": str(args.checkpoint),
        "environment": args.env,
        "seeds": args.seeds,
        "summary": summary,
        "episodes": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--architectures", nargs="+", default=["c7t", "c8t"])
    parser.add_argument("--env", default="grid_nav_vision")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(1, 41)))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = asyncio.run(_run(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"report: {args.out}")


if __name__ == "__main__":
    main()
