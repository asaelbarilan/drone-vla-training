"""Audit the additive VLA codec through existing router, controller and physics.

No learned model, architecture performance score, or evaluation seed is used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

import numpy as np

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import (
    ControlCommand,
    DecisionEnvelope,
    DecisionKind,
    MemorySnapshot,
    MissionDirective,
    MissionSpec,
    PerceptionState,
    ProgressLabel,
    TaskFamily,
    Vec3,
)
from uavlab.core.compose import load_architecture
from uavlab.core.decision_router import DecisionRouter
from uavlab.interfaces import DecisionContext
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.training.direct_vla_contract import (
    CONTRACT_ID,
    DirectVLATarget,
    action_from_target,
    target_from_command,
)

SEED = 1401
HORIZON = 0.2
DT_NS = 50_000_000


def context(mission, obs):
    return DecisionContext(
        mission=mission,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=0,
        episode_id="codec-execution-audit",
    )


def envelope(action, ctx, identity="codec-audit"):
    return DecisionEnvelope(
        decision_id=identity,
        kind=action.kind,
        payload=action,
        source_observation_seq=ctx.observation.seq,
        source_t_sim_ns=ctx.t_sim_ns,
        produced_t_wall_ns=0,
        produced_t_sim_ns=ctx.t_sim_ns,
        producer="codec_audit_not_model",
    )


async def audit():
    rng = np.random.default_rng(20260916)
    controller = MockVelocityController()
    mission = MissionSpec(
        mission_id="codec-audit",
        instruction="component audit only",
        task_family=TaskFamily.KNOWN_GOAL_NAV,
    )
    controller.reset(mission, SEED)
    arch = load_architecture("c7")
    source_env = DeterministicEnv(n_obstacles=0, n_distractors=0)
    decoded_env = DeterministicEnv(n_obstacles=0, n_distractors=0)
    await source_env.reset(mission, SEED)
    ctx = context(mission, await decoded_env.reset(mission, SEED))
    velocity_errors, yaw_errors, speed_projection = [], [], 0
    samples = []
    for i in range(4096):
        direction = rng.normal(size=3)
        direction /= np.linalg.norm(direction)
        # Includes the speed boundary to expose post-quantization norm projection.
        velocity = direction * (5.0 if i % 4 == 0 else rng.uniform(0.0, 5.0))
        yaw, yaw_rate = rng.uniform(-math.pi, math.pi), rng.uniform(-1.5, 1.5)
        teacher = ControlCommand(
            t_sim_ns=0,
            velocity=Vec3(x=velocity[0], y=velocity[1], z=velocity[2]),
            yaw_rate_rps=float(yaw_rate),
        )
        target = target_from_command(teacher, float(yaw))
        action = action_from_target(target, float(yaw), duration_s=HORIZON)
        assert action is not None
        executed = controller.from_action(action, ctx, "quantized")
        error = np.linalg.norm(np.array(executed.velocity.as_tuple()) - velocity)
        yaw_error = abs(executed.yaw_rate_rps - yaw_rate)
        assert error <= math.sqrt(3) * 5.0 / 64 + 1e-12
        assert yaw_error <= 1.5 / 64 + 1e-12
        speed_projection += int(action.velocity.norm() > 5.0)
        velocity_errors.append(float(error))
        yaw_errors.append(float(yaw_error))
        if i < 128:
            samples.append((teacher, target, float(yaw)))

    physics_checks = []
    for teacher, target, yaw in samples:
        await source_env.reset(mission, SEED)
        await decoded_env.reset(mission, SEED)
        source_env.vehicle.yaw = decoded_env.vehicle.yaw = yaw
        ctx = context(mission, await decoded_env.observe())
        action = action_from_target(target, yaw, duration_s=HORIZON)
        router = DecisionRouter(
            arch,
            verifier=None,
            planner=None,
            shield=None,
            controller=controller,
        )
        router.reset(mission, SEED)
        assert router.accept(envelope(action, ctx), ctx).accepted
        for _ in range(4):
            ctx = context(mission, await decoded_env.observe())
            executed, _, _ = router.command_for_tick(ctx)
            assert executed.source_t_sim_ns == 0
            await decoded_env.step(executed, DT_NS)
            await source_env.step(teacher, DT_NS)
        drift = float(np.linalg.norm(source_env.vehicle.position - decoded_env.vehicle.position))
        assert drift <= HORIZON * math.sqrt(3) * 5.0 / 64 + 1e-12
        yaw_drift = math.atan2(
            math.sin(source_env.vehicle.yaw - decoded_env.vehicle.yaw),
            math.cos(source_env.vehicle.yaw - decoded_env.vehicle.yaw),
        )
        assert abs(yaw_drift) <= HORIZON * 1.5 / 64 + 1e-12
        ctx = context(mission, await decoded_env.observe())
        expired, _, _ = router.command_for_tick(ctx)
        assert expired.is_hold
        physics_checks.append({"position_drift_m": drift, "yaw_drift_rad": abs(yaw_drift)})

    ctx = context(mission, await decoded_env.reset(mission, SEED))
    router = DecisionRouter(arch, verifier=None, planner=None, shield=None, controller=controller)
    router.reset(mission, SEED)
    hold = action_from_target(
        DirectVLATarget(32, 32, 32, 32), ctx.observation.yaw_rad, duration_s=HORIZON
    )
    assert router.accept(envelope(hold, ctx), ctx).accepted
    assert not router.stop_requested
    assert router.command_for_tick(ctx)[0].is_hold
    stop = MissionDirective(label=ProgressLabel.STOP, rationale="explicit test termination")
    assert stop.kind is DecisionKind.MISSION_DIRECTIVE
    assert router.accept(envelope(stop, ctx, "stop-audit"), ctx).accepted
    assert router.stop_requested
    await source_env.close()
    await decoded_env.close()
    return {
        "contract": CONTRACT_ID,
        "kind": "component_audit_not_model_or_architecture_evaluation",
        "scene_seed": SEED,
        "random_commands": len(velocity_errors),
        "velocity_error_mps": {
            "mean": float(np.mean(velocity_errors)),
            "p95": float(np.quantile(velocity_errors, 0.95)),
            "max": max(velocity_errors),
        },
        "yaw_rate_error_rps": {"mean": float(np.mean(yaw_errors)), "max": max(yaw_errors)},
        "controller_speed_projections": speed_projection,
        "physics_cases": len(physics_checks),
        "physics_steps_per_case": 4,
        "max_position_drift_m": max(r["position_drift_m"] for r in physics_checks),
        "max_yaw_drift_rad": max(r["yaw_drift_rad"] for r in physics_checks),
        "action_expiry_checks": len(physics_checks),
        "hold_stop_separation": True,
        "horizon_s": HORIZON,
        "duration_start": "router acceptance time",
        "velocity_orientation": "source-observation yaw, fixed ENU during horizon",
        "training_ready": False,
        "remaining": [
            "student observability",
            "recorded dataset alignment",
            "terminal evidence",
            "trained inference",
            "cross-domain transfer",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(audit())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
