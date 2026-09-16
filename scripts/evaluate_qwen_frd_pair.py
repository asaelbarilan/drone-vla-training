"""Offline model-driven rollout: simulation pauses during measured Qwen inference.

This isolates policy/action correctness, not deployable real-time latency.
Matched FRD base/adapter comparison on frozen validation scenes1400/1405.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from pathlib import Path

import torch
from peft import PeftModel
from run_qwen_direct_vla_overfit import MODEL, cuda, load_base
from transformers import AutoProcessor

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.analysis.flight_debugger import html_document, load_run
from uavlab.contracts import DecisionEnvelope, MissionDirective, MissionSpec, ProgressLabel
from uavlab.core.compose import load_architecture
from uavlab.core.config import EnvironmentConfig
from uavlab.core.decision_router import DecisionRouter
from uavlab.core.frame_store import global_store
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.reasoning.aerovla import make_dual_view_mosaic
from uavlab.training.direct_vla_fixture import (
    DT_NS,
    HORIZON_S,
    context,
    public_teacher,
    student_state,
    write_json,
)
from uavlab.training.direct_vla_frd import (
    CONTRACT_ID,
    action_from_target,
    parse_target,
    student_prompt,
    target_json,
)


async def rollout(model, processor, data, out, seed, adapter, wall_deadline, mode):
    original = json.loads((data / f"runs/public_goal_s{seed}/manifest.json").read_text())
    config = EnvironmentConfig.model_validate(original["environment_config"])
    mission = MissionSpec(
        mission_id=f"model-flight-{seed}",
        instruction=config.instruction,
        task_family=config.task_family,
        success=config.params["success"],
    )
    env = DeterministicEnv(**config.params)
    await env.reset(mission, seed)
    name = f"qwen_frd_{mode}_s{seed}"
    folder = out / name
    (folder / "debug/calls").mkdir(parents=True, exist_ok=False)
    (folder / "images").mkdir()
    arch = load_architecture("c7").model_copy(
        update={
            "id": f"qwen_frd_{mode}_offline_diagnostic",
            "name": "Qwen LoRA offline model actions; simulation pauses during inference",
        }
    )
    controller = MockVelocityController()
    controller.reset(mission, seed)
    router = DecisionRouter(arch, verifier=None, planner=None, shield=None, controller=controller)
    router.reset(mission, seed)
    events, calls = [], []
    reason, stopped, success = "timeout", False, False
    decision_id = None

    def emit(kind, obs, payload, trace=None):
        events.append(
            {
                "episode_id": name,
                "event_type": kind,
                "seq": len(events),
                "t_sim_ns": obs.t_sim_ns,
                "t_wall_ns": time.monotonic_ns(),
                "component": "qwen_offline_diagnostic",
                "payload": payload,
                "trace_id": trace,
            }
        )

    for tick in range(200):  # ten simulated seconds, at most50 actual generations
        obs = await env.observe()
        ctx = context(mission, obs, name)
        if tick % 4 == 0:
            if time.monotonic() >= wall_deadline:
                reason = "wall_budget"
                break
            state = student_state(obs)
            prompt = student_prompt(mission.instruction, state)
            mosaic = make_dual_view_mosaic(
                global_store().get(obs.rgb.uri), global_store().get(obs.rgb_down.uri), 224
            )
            image_path = folder / "images" / f"{tick:05d}_mosaic.png"
            mosaic.save(image_path)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": mosaic},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            text = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = processor(text=[text], images=[mosaic], return_tensors="pt")
            assert inputs.input_ids.shape[1] <= 512
            start = time.monotonic()
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                outputs = model.generate(
                    **cuda(inputs), max_new_tokens=80, do_sample=False, use_cache=True
                )
            latency = time.monotonic() - start
            raw = processor.tokenizer.decode(
                outputs[0, inputs.input_ids.shape[1] :], skip_special_tokens=True
            )
            decision_id = f"{name}-decision-{len(calls):04d}"
            teacher, expected_stop, evidence = public_teacher(
                mission.instruction, state, obs.t_sim_ns
            )
            # Teacher is evaluation-only; never replaces invalid/model actions.
            error = None
            try:
                target = parse_target(raw)
                stopped = target.stop
                action = action_from_target(target, obs.yaw_rad, duration_s=HORIZON_S)
                if stopped:
                    action = MissionDirective(
                        label=ProgressLabel.STOP, rationale="actual model stop"
                    )
                parsed = json.loads(target_json(target))
            except ValueError as exc:
                error, parsed = str(exc), None
                reason = "invalid_model_output"
            call = {
                "role": "policy",
                "observation_seq": obs.seq,
                "requested_t_sim_ns": obs.t_sim_ns,
                "completed_t_sim_ns": obs.t_sim_ns,
                "prompt": prompt,
                "response": raw,
                "response_schema": {"contract": CONTRACT_ID},
                "image_files": [image_path.relative_to(folder).as_posix()],
                "latency_s": latency,
                "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "simulation_paused_during_inference": True,
                "parsed": parsed,
                "parse_error": error,
                "evaluation_only": evidence,
            }
            write_json(folder / "debug/calls" / f"{len(calls):04d}.json", call)
            calls.append(call)
            emit(
                "inference_call",
                obs,
                {
                    "role": "policy",
                    "model_id": f"Qwen3-VL-4B-Instruct/{mode}/FRD",
                    "latency_ms": latency * 1000,
                },
                decision_id,
            )
            if error:
                # Explicit hold and terminate invalid-output rollout, no teacher fallback.
                command = controller.hold(ctx)
            else:
                proposal = DecisionEnvelope(
                    decision_id=decision_id,
                    kind=action.kind,
                    payload=action,
                    source_observation_seq=obs.seq,
                    source_t_sim_ns=obs.t_sim_ns,
                    produced_t_wall_ns=time.monotonic_ns(),
                    produced_t_sim_ns=obs.t_sim_ns,
                    producer=f"actual_qwen_frd_{mode}",
                    provenance={
                        "target": target_json(target),
                        "source_yaw": repr(obs.yaw_rad),
                        "note": "Offline action test: simulator paused during inference",
                    },
                )
                emit("decision_proposed", obs, proposal.model_dump(mode="json"), decision_id)
                outcome = router.accept(proposal, ctx)
                if not outcome.accepted:
                    raise ValueError(f"model action rejected: {outcome.reason}")
                emit("decision_executed", obs, {"accepted": True}, decision_id)
                command = controller.hold(ctx) if stopped else router.command_for_tick(ctx)[0]
                if stopped:
                    success = expected_stop
                    reason = "agent_stopped" if success else "false_stop"
            print(
                json.dumps(
                    {
                        "seed": seed,
                        "tick": tick,
                        "raw": raw,
                        "latency_s": latency,
                        "goal_error_m": evidence["public_goal_error_m"],
                        "stop": stopped,
                    }
                ),
                flush=True,
            )
        else:
            command = router.command_for_tick(ctx)[0]
        emit(
            "control",
            obs,
            {
                "position_x": obs.position.x,
                "position_y": obs.position.y,
                "position_z": obs.position.z,
                "observed_velocity": list(obs.velocity.as_tuple()),
                "yaw_rad": obs.yaw_rad,
                "observation_seq": obs.seq,
                "vx": command.velocity.x,
                "vy": command.velocity.y,
                "vz": command.velocity.z,
                "yaw_rate": command.yaw_rate_rps,
                "command": command.model_dump(mode="json"),
            },
            decision_id,
        )
        await env.step(command, DT_NS)
        status = env.status()
        if status.collided or status.out_of_bounds:
            success, reason = False, "collision_or_out_of_bounds"
            break
        if stopped or reason == "invalid_model_output":
            break
    status = env.status()
    result = {
        "success": success,
        "termination_reason": reason,
        "sim_duration_s": env._t_ns / 1e9,
        "used_privileged_observations": False,
        "metrics": {
            "distance_to_goal_m": status.distance_to_goal_m,
            "collisions": float(status.collision_count),
        },
        "status": status.model_dump(mode="json"),
        "model_calls": len(calls),
        "simulation_paused_during_inference": True,
        "real_time_capable_claim": False,
        "split": "val" if seed % 5 == 0 else "train_diagnostic",
        "latencies_s": [c["latency_s"] for c in calls],
    }
    original.update(
        architecture_config=arch.model_dump(mode="json"),
        git_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        git_dirty=True,
        model_calls=len(calls),
        setup_ticks=0,
        setup_yaw_rate_rps=0.0,
        rollout_max_sim_seconds=10.0,
        adapter=str(adapter) if mode == "trained" else None,
        contract=CONTRACT_ID,
        comparison_mode=mode,
        validation_kind="offline model diagnostic; inference latency NOT charged to simulation",
    )
    write_json(folder / "manifest.json", original)
    write_json(folder / "result.json", result)
    (folder / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    await env.close()
    return folder, result


async def main(args):
    args.out.mkdir(parents=True, exist_ok=False)
    torch.cuda.set_per_process_memory_fraction(0.70)
    processor = AutoProcessor.from_pretrained(str(MODEL), local_files_only=True)
    model = load_base().eval()
    results, runs = [], []
    for mode in ("zero_shot", "trained"):
        if mode == "trained":
            model = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False).eval()
        deadline = time.monotonic() + 1200
        for seed in (1400, 1405):
            if time.monotonic() >= deadline:
                raise RuntimeError("matched comparison wall budget exhausted")
            folder, result = await rollout(
                model, processor, args.data, args.out, seed, args.adapter, deadline, mode
            )
            results.append({"seed": seed, "mode": mode, **result})
            run = await load_run(folder)
            for decision in run["decisions"]:
                rec = decision["recording"]
                if rec:
                    decision["payload"]["evidence"] = json.dumps(
                        {
                            "actual_prediction": rec["parsed"],
                            "mode": mode,
                            "contract": CONTRACT_ID,
                            "inference_seconds": rec["latency_s"],
                            "simulation_paused_during_inference": True,
                            "evaluation_only": rec["evaluation_only"],
                        },
                        indent=2,
                    )
            runs.append(run)
            write_json(
                args.out / "summary.json",
                {
                    "results": results,
                    "contract": CONTRACT_ID,
                    "matched_conditions": True,
                    "real_time_capable_claim": False,
                },
            )
            (args.out / "model_flights.html").write_text(
                html_document({"schema": 1, "runs": runs, "sources": {}}), encoding="utf-8"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
