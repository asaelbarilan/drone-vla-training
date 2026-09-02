"""Run the predeclared local-simulator acceptance gate for SUPER.

Development seeds are deliberately fixed at 1000-1019. This script never uses
the held-out evaluation seeds 1-40 and does not tune parameters.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator

DEV_SEEDS = tuple(range(1000, 1020))
REQUIREMENTS = {
    "grid_nav": 19,
    "failure_recovery": 18,
}


def run_episode(config_root: Path, environment_id: str, seed: int):
    architecture = load_architecture("c0", config_root)
    environment = load_environment(environment_id, config_root)
    orchestrator = Orchestrator(
        architecture,
        environment,
        EpisodeSpec(episode_id=f"super_gate__{environment_id}__s{seed}", seed=seed),
    )
    return asyncio.run(orchestrator.run())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "configs",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    architecture = load_architecture("c0", args.config_root)
    if architecture.planner is None or architecture.planner.name != "super_local":
        raise SystemExit("C0 does not select planner/super_local")

    report: dict[str, object] = {
        "paper": "SUPER",
        "architecture": "c0",
        "planner": architecture.planner.name,
        "development_seeds": list(DEV_SEEDS),
        "held_out_seeds_used": [],
        "regimes": {},
    }
    passed = True
    for environment_id, required_successes in REQUIREMENTS.items():
        results = [run_episode(args.config_root, environment_id, seed) for seed in DEV_SEEDS]
        successes = sum(result.success for result in results)
        collisions = sum(result.metrics["collisions"] for result in results)
        interventions = sum(result.metrics["safety_interventions"] for result in results)
        regime_passed = (
            successes >= required_successes
            and collisions == 0.0
            and interventions == 0.0
        )
        passed &= regime_passed
        report["regimes"][environment_id] = {
            "required_successes": required_successes,
            "successes": successes,
            "collisions": collisions,
            "downstream_shield_interventions": interventions,
            "plans_infeasible": sum(
                result.metrics["router_plans_infeasible"] for result in results
            ),
            "passed": regime_passed,
            "failures": [
                {
                    "seed": result.seed,
                    "termination": result.termination_reason.value,
                    "distance_to_goal_m": result.metrics["distance_to_goal_m"],
                    "collisions": result.metrics["collisions"],
                }
                for result in results
                if not result.success
            ],
        }

    first = run_episode(args.config_root, "grid_nav", DEV_SEEDS[0])
    second = run_episode(args.config_root, "grid_nav", DEV_SEEDS[0])
    deterministic_fields = (
        "path_length_m",
        "distance_to_goal_m",
        "collisions",
        "decisions_executed",
        "router_plans_infeasible",
    )
    deterministic = all(first.metrics[key] == second.metrics[key] for key in deterministic_fields)
    report["deterministic_repeat"] = {
        "seed": DEV_SEEDS[0],
        "fields": list(deterministic_fields),
        "passed": deterministic,
    }
    passed &= deterministic
    report["passed"] = passed

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
