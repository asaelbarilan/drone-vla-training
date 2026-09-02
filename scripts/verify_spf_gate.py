"""Run the predeclared real-VLM local-simulator gate for SPF/C2.

Only development seeds 1040-1044 are used. The RGB-only environments expose
neither depth frames nor privileged goal coordinates to the policy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request
from pathlib import Path
from typing import Any

from uavlab.contracts import EventType
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator

DEV_SEEDS = tuple(range(1040, 1045))
REGIMES = {
    "grid_nav": ("grid_nav_rgb", 4),
    "object_search": ("object_search_rgb", 2),
}


def model_resource(host: str, model_id: str, expected_digest: str) -> dict[str, Any]:
    """Resolve the exact local model artifact declared by the config."""

    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=10) as response:
            payload = json.load(response)
    except (OSError, ValueError) as exc:
        return {
            "model_id": model_id,
            "expected_digest": expected_digest,
            "digest": None,
            "available": False,
            "error": str(exc),
        }
    for model in payload.get("models", []):
        if model.get("name") == model_id or model.get("model") == model_id:
            digest = str(model.get("digest") or "")
            return {
                "model_id": model_id,
                "expected_digest": expected_digest,
                "digest": digest,
                "size": model.get("size"),
                "details": model.get("details", {}),
                "available": bool(expected_digest) and digest == expected_digest,
            }
    return {
        "model_id": model_id,
        "expected_digest": expected_digest,
        "digest": None,
        "available": False,
    }


def run_episode(config_root: Path, environment_id: str, seed: int, out_root: Path):
    architecture = load_architecture("c2_spf", config_root)
    environment = load_environment(environment_id, config_root)
    episode_id = f"spf_gate__{environment_id}__s{seed}"
    out_dir = out_root / episode_id
    orchestrator = Orchestrator(
        architecture,
        environment,
        EpisodeSpec(episode_id=episode_id, seed=seed),
        out_dir=out_dir,
    )
    result = asyncio.run(orchestrator.run())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2), encoding="utf-8"
    )

    decisions = []
    for event in orchestrator.log.of_type(EventType.DECISION_PROPOSED):
        if event.component != "policy" or event.payload.get("producer") != "spf_waypoint":
            continue
        provenance = event.payload.get("provenance", {})
        if not isinstance(provenance, dict):
            provenance = {}
        decisions.append(
            {
                "kind": event.payload.get("kind"),
                "u": provenance.get("spf_u"),
                "v": provenance.get("spf_v"),
                "distance": provenance.get("spf_distance_label"),
                "step_m": provenance.get("spf_step_m"),
                "source_observation_seq": event.payload.get("source_observation_seq"),
            }
        )
    mechanism = {
        "policy_inference_calls": sum(
            event.payload.get("role") == "policy"
            for event in orchestrator.log.of_type(EventType.INFERENCE_CALL)
        ),
        "typed_decisions": len(decisions),
        "super_plans": sum(
            event.payload.get("planner") == "super_local"
            for event in orchestrator.log.of_type(EventType.PLAN)
        ),
        "verifier_events": orchestrator.log.count(EventType.VERIFIER),
        "raw_model_text_logged": any(
            any(key in event.payload for key in ("raw", "response", "model_output"))
            for event in orchestrator.log.events
        ),
    }
    return result, decisions, mechanism


def main() -> int:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--config-root", type=Path, default=root / "configs")
    parser.add_argument(
        "--run-root",
        type=Path,
        default=root / "reports" / "paper_implementation" / "spf_gate_runs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "reports" / "paper_implementation" / "spf_gate.json",
    )
    args = parser.parse_args()

    architecture = load_architecture("c2_spf", args.config_root)
    inference_params = architecture.inference.params
    model_id = str(inference_params.get("model_id", ""))
    expected_digest = str(inference_params.get("expected_digest", ""))
    configuration_ok = (
        architecture.policy.name == "spf_waypoint"
        and architecture.inference.name == "ollama"
        and architecture.planner is not None
        and architecture.planner.name == "super_local"
        and architecture.verifier is None
        and not architecture.allow_privileged_observations
        and "script" not in architecture.policy.name
        and "oracle" not in architecture.policy.name
    )
    resource = model_resource(
        str(inference_params.get("host", "")), model_id, expected_digest
    )
    passed = configuration_ok and bool(resource["available"])
    report: dict[str, Any] = {
        "paper": "See, Point, Fly",
        "architecture": "c2_spf",
        "development_seeds": list(DEV_SEEDS),
        "held_out_seeds_used": [],
        "configuration_ok": configuration_ok,
        "model_resource": resource,
        "regimes": {},
    }

    args.run_root.mkdir(parents=True, exist_ok=True)
    for regime_name, (environment_id, required_successes) in REGIMES.items():
        runs = [
            run_episode(args.config_root, environment_id, seed, args.run_root)
            for seed in DEV_SEEDS
        ]
        results = [run[0] for run in runs]
        successes = sum(result.success for result in results)
        collisions = sum(result.metrics.get("collisions", 0.0) for result in results)
        invalid_outputs = sum(
            result.metrics.get("spf_invalid_outputs", 0.0) for result in results
        )
        runtime_errors = sum(result.error is not None for result in results)
        mechanism_ok = all(
            mechanism["policy_inference_calls"] > 0
            and mechanism["typed_decisions"] > 0
            and mechanism["super_plans"] > 0
            and mechanism["verifier_events"] == 0
            and not mechanism["raw_model_text_logged"]
            for _, _, mechanism in runs
        )
        terminal_rule_ok = all(
            (not result.success)
            or (
                result.metrics.get("spf_stop_outputs", 0.0) == 1.0
                and result.metrics.get("correct_terminal_stop", 0.0) == 1.0
            )
            for result in results
        )
        regime_passed = (
            successes >= required_successes
            and collisions == 0.0
            and invalid_outputs == 0.0
            and runtime_errors == 0
            and mechanism_ok
            and terminal_rule_ok
            and all(not result.used_privileged_observations for result in results)
        )
        passed &= regime_passed
        report["regimes"][regime_name] = {
            "environment_profile": environment_id,
            "required_successes": required_successes,
            "successes": successes,
            "collisions": collisions,
            "invalid_outputs": invalid_outputs,
            "runtime_errors": runtime_errors,
            "mechanism_observed_every_run": mechanism_ok,
            "terminal_rule_ok": terminal_rule_ok,
            "passed": regime_passed,
            "runs": [
                {
                    "seed": result.seed,
                    "success": result.success,
                    "termination": result.termination_reason.value,
                    "distance_to_goal_m": result.metrics["distance_to_goal_m"],
                    "reached_goal": result.metrics.get("reached_goal", 0.0),
                    "valid_outputs": result.metrics.get("spf_valid_outputs", 0.0),
                    "invalid_outputs": result.metrics.get("spf_invalid_outputs", 0.0),
                    "stop_outputs": result.metrics.get("spf_stop_outputs", 0.0),
                    "decisions": decisions,
                    "mechanism": mechanism,
                }
                for result, decisions, mechanism in runs
            ],
        }

    first = run_episode(args.config_root, "grid_nav_rgb", DEV_SEEDS[0], args.run_root)
    second = run_episode(args.config_root, "grid_nav_rgb", DEV_SEEDS[0], args.run_root)
    distance_delta = abs(
        first[0].metrics["distance_to_goal_m"] - second[0].metrics["distance_to_goal_m"]
    )
    deterministic = (
        first[0].success == second[0].success
        and first[0].termination_reason == second[0].termination_reason
        and first[1] == second[1]
        and distance_delta <= 0.25
    )
    report["deterministic_repeat"] = {
        "seed": DEV_SEEDS[0],
        "same_success": first[0].success == second[0].success,
        "same_termination": first[0].termination_reason == second[0].termination_reason,
        "same_exact_typed_sequence": first[1] == second[1],
        "first_sequence": first[1],
        "second_sequence": second[1],
        "final_distance_delta_m": distance_delta,
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
