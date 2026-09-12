"""D-102: replay gates and probe SUPER on rejected goals, without inference."""

import asyncio
import copy
import json
import math
from pathlib import Path

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import (
    ControlCommand,
    DecisionEnvelope,
    MemorySnapshot,
    MissionConstraints,
    MissionSpec,
    PerceptionState,
    SuccessCriteria,
    Vec3,
)
from uavlab.core.config import ArchitectureConfig
from uavlab.core.registry import REGISTRY
from uavlab.interfaces import DecisionContext

ROOT = Path("runs/vlm_adaptive_plan_20260912_s1061")
OUT = Path("reports/adaptive_plan_flights_20260912")


def context(mission, obs, now):
    return DecisionContext(
        mission=mission,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=now,
        t_wall_ns=0,
        episode_id="offline_gate_probe",
    )


async def main():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    events = [
        json.loads(x) for x in (ROOT / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    ec = manifest["environment_config"]
    params = {**ec["params"], **ec["adapter"]["params"], "allow_privileged": False}
    mission = MissionSpec(
        mission_id="offline_gate_probe",
        instruction=ec["instruction"],
        task_family=ec["task_family"],
        constraints=MissionConstraints.model_validate(params["constraints"]),
        success=SuccessCriteria.model_validate(params.get("success", {})),
    )
    planner = REGISTRY.build("planner", arch.planner.name, arch.planner.params)
    gate = REGISTRY.build("verifier", arch.verifier.name, arch.verifier.params)
    for obj in (planner, gate):
        obj.reset(mission, 1061)
    logged_gates = {e["trace_id"]: e["payload"] for e in events if e["event_type"] == "verifier"}
    logged_plans = {e["trace_id"]: e["payload"] for e in events if e["event_type"] == "plan"}
    env = DeterministicEnv(**params)
    obs = await env.reset(mission, 1061)
    checks = {"poses": 0, "gate_results": 0, "accepted_plans": 0}
    probes = []
    for event in events:
        if event["t_sim_ns"] > 32_000_000_000:
            break
        p = event["payload"]
        if event["event_type"] == "control":
            obs = await env.observe()
            assert (
                math.dist(
                    [obs.position.x, obs.position.y, obs.position.z],
                    [p["position_" + a] for a in "xyz"],
                )
                < 1e-9
            )
            checks["poses"] += 1
            await env.step(
                ControlCommand(
                    t_sim_ns=event["t_sim_ns"],
                    velocity=Vec3(x=p["vx"], y=p["vy"], z=p["vz"]),
                    yaw_rate_rps=p["yaw_rate"],
                ),
                50_000_000,
            )
        elif event["event_type"] == "decision_proposed" and "producer" in p:
            envelope = DecisionEnvelope.model_validate(
                {
                    "decision_id": event["trace_id"],
                    "kind": p["kind"],
                    "payload": p["decision_payload"],
                    "source_observation_seq": p["source_observation_seq"],
                    "source_t_sim_ns": event["t_sim_ns"] - round(p["production_latency_s"] * 1e9),
                    "produced_t_sim_ns": event["t_sim_ns"],
                    "produced_t_wall_ns": event["t_wall_ns"],
                    "producer": p["producer"],
                    "provenance": p["provenance"],
                }
            )
            ctx = context(mission, obs, event["t_sim_ns"])
            result = gate.verify(envelope, ctx)
            logged = logged_gates[event["trace_id"]]
            assert result.accepted == logged["accepted"] and result.reason == logged["reason"]
            checks["gate_results"] += 1
            if result.accepted:
                trajectory = planner.plan(envelope.payload, ctx)
                assert trajectory.metadata == logged_plans[event["trace_id"]]["planner_metadata"]
                checks["accepted_plans"] += 1
            elif event["t_sim_ns"] in (19_000_000_000, 32_000_000_000):
                # Isolated copy: probe must never alter the historical replay state.
                branch = copy.deepcopy(planner)
                trajectory = branch.plan(envelope.payload, ctx)
                probes.append(
                    {
                        "available_s": event["t_sim_ns"] / 1e9,
                        "execution_observation_s": obs.t_sim_ns / 1e9,
                        "decision_id": event["trace_id"],
                        "position": obs.position.model_dump(),
                        "proposed_goal": envelope.payload.target.model_dump(),
                        "original_gate": result.reason,
                        "counterfactual_super_feasible": trajectory.feasible,
                        "counterfactual_reason": trajectory.reason,
                        "metadata": trajectory.metadata,
                        "trajectory": trajectory.model_dump(mode="json"),
                    }
                )
    await env.close()
    report = {
        "scope": (
            "No inference, no continuation flight, no verifier/config change. "
            "Local planning feasibility only."
        ),
        "checks": checks,
        "probes": probes,
    }
    (OUT / "REJECTION_PROBE.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "checks": checks,
                "probes": [{k: v for k, v in p.items() if k != "trajectory"} for p in probes],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
