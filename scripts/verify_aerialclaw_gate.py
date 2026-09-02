"""Run the predeclared real-model local-simulator gate for AerialClaw/C1."""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request
from pathlib import Path

from uavlab.contracts import EventType
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator

DEV_SEEDS = tuple(range(1020, 1025))
REQUIREMENTS = {"grid_nav": 4, "object_search": 2}
MODEL_ID = "gpt-oss:20b"
MODEL_DIGEST = "17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7"


def typed_signature(decisions: list[dict[str, object]]) -> list[dict[str, object]]:
    """The predeclared typed sequence: ordered decision kind and skill.

    Continuous sensor-derived coordinates, tolerances and free-text stop
    reasons remain in the full report and are compared indirectly through the
    final-distance tolerance.  They are arguments to a typed decision, not its
    type.
    """

    return [
        {"kind": decision.get("kind"), "skill": decision.get("skill")}
        for decision in decisions
    ]


def model_resource(host: str) -> dict[str, object]:
    with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=10) as response:
        payload = json.load(response)
    for model in payload.get("models", []):
        if model.get("name") == MODEL_ID or model.get("model") == MODEL_ID:
            return {
                "model_id": MODEL_ID,
                "digest": model.get("digest"),
                "size": model.get("size"),
                "details": model.get("details", {}),
                "available": model.get("digest") == MODEL_DIGEST,
            }
    return {"model_id": MODEL_ID, "digest": None, "available": False}


def run_episode(config_root: Path, environment_id: str, seed: int, out_root: Path):
    architecture = load_architecture("c1", config_root)
    environment = load_environment(environment_id, config_root)
    episode_id = f"aerialclaw_gate__{environment_id}__s{seed}"
    orchestrator = Orchestrator(
        architecture,
        environment,
        EpisodeSpec(episode_id=episode_id, seed=seed),
        out_dir=out_root / episode_id,
    )
    result = asyncio.run(orchestrator.run())
    decisions = [
        {
            "kind": event.payload.get("kind"),
            "skill": event.payload.get("skill_name"),
            "args": event.payload.get("skill_args"),
        }
        for event in orchestrator.log.of_type(EventType.DECISION_PROPOSED)
        if event.component == "policy"
        and event.payload.get("producer") == "aerialclaw_agent"
        and not event.payload.get("rejected")
    ]
    mechanism = {
        "inference_calls": orchestrator.log.count(EventType.INFERENCE_CALL),
        "typed_decisions": len(decisions),
        "super_plans": sum(
            event.payload.get("planner") == "super_local"
            for event in orchestrator.log.of_type(EventType.PLAN)
        ),
        "verifier_events": orchestrator.log.count(EventType.VERIFIER),
    }
    return result, decisions, mechanism


def main() -> int:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--config-root", type=Path, default=root / "configs")
    parser.add_argument(
        "--run-root",
        type=Path,
        default=root / "reports" / "paper_implementation" / "aerialclaw_gate_runs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "reports" / "paper_implementation" / "aerialclaw_gate.json",
    )
    args = parser.parse_args()

    architecture = load_architecture("c1", args.config_root)
    configuration_ok = (
        architecture.policy.name == "aerialclaw_agent"
        and architecture.inference.name == "ollama"
        and architecture.planner is not None
        and architecture.planner.name == "super_local"
        and not architecture.allow_privileged_observations
        and "script" not in architecture.policy.name
        and "oracle" not in architecture.policy.name
    )
    resource = model_resource(str(architecture.inference.params.get("host", "")))
    passed = configuration_ok and bool(resource["available"])
    report: dict[str, object] = {
        "paper": "AerialClaw",
        "architecture": "c1",
        "development_seeds": list(DEV_SEEDS),
        "held_out_seeds_used": [],
        "configuration_ok": configuration_ok,
        "model_resource": resource,
        "regimes": {},
    }

    args.run_root.mkdir(parents=True, exist_ok=True)
    for environment_id, required_successes in REQUIREMENTS.items():
        runs = [
            run_episode(args.config_root, environment_id, seed, args.run_root)
            for seed in DEV_SEEDS
        ]
        results = [run[0] for run in runs]
        successes = sum(result.success for result in results)
        collisions = sum(result.metrics["collisions"] for result in results)
        runtime_errors = sum(result.error is not None for result in results)
        mechanism_ok = all(
            mechanism["inference_calls"] > 0
            and mechanism["typed_decisions"] > 0
            and mechanism["super_plans"] > 0
            for _, _, mechanism in runs
        )
        regime_passed = (
            successes >= required_successes
            and collisions == 0.0
            and runtime_errors == 0
            and mechanism_ok
            and all(not result.used_privileged_observations for result in results)
        )
        passed &= regime_passed
        report["regimes"][environment_id] = {  # type: ignore[index]
            "required_successes": required_successes,
            "successes": successes,
            "collisions": collisions,
            "runtime_errors": runtime_errors,
            "mechanism_observed_every_run": mechanism_ok,
            "passed": regime_passed,
            "runs": [
                {
                    "seed": result.seed,
                    "success": result.success,
                    "termination": result.termination_reason.value,
                    "distance_to_goal_m": result.metrics["distance_to_goal_m"],
                    "calls": result.metrics.get("aerialclaw_calls", 0.0),
                    "parse_failures": result.metrics.get("aerialclaw_parse_failures", 0.0),
                    "typed_sequence": decisions,
                    "mechanism": mechanism,
                }
                for (result, decisions, mechanism) in runs
            ],
        }

    first = run_episode(args.config_root, "grid_nav", DEV_SEEDS[0], args.run_root)
    second = run_episode(args.config_root, "grid_nav", DEV_SEEDS[0], args.run_root)
    first_signature = typed_signature(first[1])
    second_signature = typed_signature(second[1])
    same_sequence = first_signature == second_signature
    same_exact_arguments = first[1] == second[1]
    final_distance_delta = abs(
        first[0].metrics["distance_to_goal_m"] - second[0].metrics["distance_to_goal_m"]
    )
    deterministic = (
        first[0].success == second[0].success
        and first[0].termination_reason == second[0].termination_reason
        and same_sequence
        and final_distance_delta <= 0.25
    )
    report["deterministic_repeat"] = {
        "seed": DEV_SEEDS[0],
        "same_success": first[0].success == second[0].success,
        "same_termination": first[0].termination_reason == second[0].termination_reason,
        "same_typed_sequence": same_sequence,
        "typed_signature_definition": "ordered (decision kind, skill) pairs",
        "first_typed_signature": first_signature,
        "second_typed_signature": second_signature,
        "same_exact_arguments": same_exact_arguments,
        "first_full_sequence": first[1],
        "second_full_sequence": second[1],
        "final_distance_delta_m": final_distance_delta,
        "tolerance_m": 0.25,
        "passed": deterministic,
    }
    passed &= deterministic
    report["passed"] = passed

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
