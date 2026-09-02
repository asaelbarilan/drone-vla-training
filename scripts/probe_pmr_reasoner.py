"""Run the frozen PMR JSON/skill contract against the configured real model.

This is a static capability probe, not an architecture score. It bypasses only
learned admission (whose checkpoint is trained later); the recovery component,
model routing, strict parser, and local symbolic grounding are the production
implementations selected by the C6 PMR YAML profile.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from uavlab.contracts import (
    DecisionKind,
    Detection,
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    OccupancyHint,
    PerceptionState,
    ProgressLabel,
    ProgressState,
    RecoveryRequest,
    RecoveryTrigger,
    TaskFamily,
    Vec3,
)
from uavlab.core.clock import SimClock
from uavlab.core.compose import load_architecture
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, RoutingFeedback


def _context(case: str) -> DecisionContext:
    t_ns = 1_000_000_000
    obs = ObservationPacket(
        seq=1,
        t_sim_ns=t_ns,
        t_wall_ns=t_ns,
        position=Vec3(x=1.0, y=2.0, z=3.0),
        velocity=Vec3(x=0.1, y=0.0, z=0.0),
        yaw_rad=0.2,
        battery_frac=0.75,
    )
    target = Detection(
        label="target",
        score=0.82,
        position=Vec3(x=8.0, y=4.0, z=3.0),
        distance_m=7.3,
    )
    if case == "blocked":
        label = ProgressLabel.BLOCKED
        detections = (target,)
        clearance = 0.8
        uncertainty = 0.25
        feedback_reason = "planner infeasible"
    elif case == "target_lost":
        label = ProgressLabel.LOST
        detections = ()
        clearance = 5.0
        uncertainty = 0.9
        feedback_reason = "target evidence unavailable"
    else:
        label = ProgressLabel.CONTINUE
        detections = (target,)
        clearance = 5.0
        uncertainty = 0.2
        feedback_reason = "waypoint planned but progress stalled"
    mission = MissionSpec(
        mission_id=f"pmr-probe:{case}",
        instruction="find the red target and stop safely",
        task_family=TaskFamily.FAILURE_RECOVERY,
        allowed_skills=(
            "goto",
            "approach",
            "hover",
            "scan",
            "back_off",
            "ascend",
            "stop",
        ),
    )
    return DecisionContext(
        mission=mission,
        observation=obs,
        perception=PerceptionState(
            observation_seq=obs.seq,
            t_sim_ns=t_ns,
            detections=detections,
            geometry=OccupancyHint(free_radius_m=clearance),
            uncertainty=uncertainty,
        ),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=t_ns),
        t_sim_ns=t_ns,
        t_wall_ns=t_ns,
        episode_id=f"pmr-probe:{case}",
        last_progress=ProgressState(
            label=label,
            observation_seq=obs.seq,
            t_sim_ns=t_ns,
            stalled_for_s=4.0,
            evidence=feedback_reason,
        ),
        last_routing_feedback=RoutingFeedback(
            decision_id="previous",
            accepted=False,
            reason=feedback_reason,
            proposed_kind=DecisionKind.WAYPOINT,
            expanded_kind=None,
            t_sim_ns=t_ns,
        ),
    )


async def _run(architecture: str, out: Path) -> int:
    arch = load_architecture(architecture)
    assert arch.recovery is not None
    backend = REGISTRY.build("inference", arch.inference.name, arch.inference.params)
    reasoner = REGISTRY.build("recovery", arch.recovery.name, arch.recovery.params)
    services = RuntimeServices(
        clock=SimClock(start_ns=1_000_000_000),
        log=EventLog("pmr-static-probe", None),
        feature_cache=FeatureCache(),
        inference=backend,
    )
    # Deliberately bind only the recovery plugin. The static probe records live
    # wall latency returned by Ollama but does not charge a simulated episode.
    bind(reasoner, services)
    rows = []
    try:
        allowed_by_case = {
            "blocked": {"local_repair", "safe_hold_verify"},
            "target_lost": {"goal_alignment", "safe_hold_verify"},
            "stalled": {"goal_resume", "local_continue"},
        }
        for index, case in enumerate(("blocked", "target_lost", "stalled")):
            ctx = _context(case)
            reasoner.reset(ctx.mission, 3000 + index)
            request = RecoveryRequest(
                trigger=RecoveryTrigger(
                    name="learned_cvi",
                    fired_t_sim_ns=ctx.t_sim_ns,
                    observation_seq=ctx.observation.seq,
                    cause=case,
                ),
                state_summary=f"Static sensor-grounded PMR probe: {case}",
                allowed_skills=ctx.mission.allowed_skills,
                call_index=index,
            )
            envelope = await reasoner.recover(request, ctx)
            assert envelope is not None
            decision = envelope.provenance.get("agent_decision")
            used_fallback = decision == "local_fallback"
            rows.append(
                {
                    "case": case,
                    "kind": envelope.kind.value,
                    "skill": getattr(envelope.payload, "skill_name", None),
                    "decision": decision,
                    "option": envelope.provenance.get("suggested_option"),
                    "risk": envelope.provenance.get("risk"),
                    "confidence": envelope.confidence,
                    "used_fallback": used_fallback,
                    "semantically_valid": not used_fallback
                    and decision in allowed_by_case[case],
                }
            )
    finally:
        close = getattr(backend, "close", None)
        if callable(close):
            close()
    report = {
        "architecture": architecture,
        "model": arch.recovery.params.get("model_id"),
        "probe_kind": "static_capability_not_architecture_score",
        "cases": rows,
        "passed": all(row["semantically_valid"] for row in rows),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture", default="c6_pmr_qwen4_gptoss")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/paper_implementation/pmr_reasoner_static_probe.json"),
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.architecture, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
