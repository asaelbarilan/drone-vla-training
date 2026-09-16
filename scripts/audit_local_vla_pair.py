"""Verify saved model-flight source frames, prompts, decoded controls and replay."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from audit_direct_vla_fixture import image_bytes

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.analysis.flight_debugger import load_run
from uavlab.contracts import ControlCommand, MissionSpec
from uavlab.core.frame_store import global_store
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.reasoning.aerovla import make_dual_view_mosaic
from uavlab.training.direct_vla_fixture import (
    DT_NS,
    HORIZON_S,
    context,
    student_state,
)
from uavlab.training.direct_vla_frd import (
    CONTRACT_ID,
    action_from_target,
    parse_target,
    student_prompt,
    target_json,
)


async def audit(root):
    summaries = []
    prefixes = {p.name.split("_frd_")[0] for p in root.glob("*_frd_*_s*")}
    assert len(prefixes) == 1
    prefix = prefixes.pop()
    for folder in sorted(root.glob("*_frd_*_s*")):
        if not (folder / "result.json").exists():
            continue
        manifest = json.loads((folder / "manifest.json").read_text())
        seed = manifest["seeds"][0]
        assert seed in (1400, 1405)
        assert manifest["contract"] == CONTRACT_ID
        config = manifest["environment_config"]
        mission = MissionSpec(
            mission_id=f"audit-{seed}",
            instruction=config["instruction"],
            task_family=config["task_family"],
            success=config["params"]["success"],
        )
        env = DeterministicEnv(**config["params"])
        await env.reset(mission, seed)
        controller = MockVelocityController()
        controller.reset(mission, seed)
        calls = {
            json.loads(p.read_text())["observation_seq"]: json.loads(p.read_text())
            for p in (folder / "debug/calls").glob("*.json")
        }
        events = [json.loads(x) for x in (folder / "events.jsonl").read_text().splitlines()]
        images = controls = 0
        action, target, source_t = None, None, None
        for event in events:
            if event["event_type"] != "control":
                continue
            obs = await env.observe()
            payload = event["payload"]
            assert obs.seq == payload["observation_seq"]
            ctx = context(mission, obs, folder.name)
            if obs.seq in calls:
                call = calls[obs.seq]
                assert call["prompt"] == student_prompt(mission.instruction, student_state(obs))
                mosaic = make_dual_view_mosaic(
                    global_store().get(obs.rgb.uri), global_store().get(obs.rgb_down.uri), 224
                )
                original = (folder / call["image_files"][0]).read_bytes()
                assert image_bytes(mosaic) == original
                assert hashlib.sha256(original).hexdigest() == call["image_sha256"]
                images += 1
                if call["parse_error"] is None:
                    target = parse_target(call["response"])
                    assert json.loads(target_json(target)) == call["parsed"]
                    action = action_from_target(target, obs.yaw_rad, duration_s=HORIZON_S)
                else:
                    target, action = None, None
                source_t = obs.t_sim_ns
            expected = (
                controller.hold(ctx)
                if action is None
                else controller.from_action(action, ctx, event["trace_id"])
            )
            actual = ControlCommand.model_validate(payload["command"])
            assert expected.velocity == actual.velocity
            assert expected.yaw_rate_rps == actual.yaw_rate_rps
            assert expected.expires_t_sim_ns == actual.expires_t_sim_ns
            assert obs.t_sim_ns - source_t < int(HORIZON_S * 1e9)
            assert (actual.velocity.x, actual.velocity.y, actual.velocity.z) == (
                payload["vx"],
                payload["vy"],
                payload["vz"],
            )
            await env.step(actual, DT_NS)
            controls += 1
        assert images == len(calls)
        await env.close()
        run = await load_run(folder)
        assert run["provenance"]["missing_source_frames"] == 0
        assert all(d["recording"] is not None for d in run["decisions"])
        summaries.append(
            {
                "seed": seed,
                "mode": manifest["comparison_mode"],
                "checked_original_mosaics_and_prompts": images,
                "checked_decoded_controls": controls,
                "replay": run["provenance"],
                "result": run["result"],
            }
        )
    assert {(r["seed"], r["mode"]) for r in summaries} == {
        (s, m) for s in (1400, 1405) for m in ("zero_shot", "trained")
    }
    assert len(summaries) == 4
    matched = []
    for seed in (1400, 1405):
        folders = [root / f"{prefix}_frd_{mode}_s{seed}" for mode in ("zero_shot", "trained")]
        manifests = [json.loads((f / "manifest.json").read_text()) for f in folders]
        first = [json.loads((f / "debug/calls/0000.json").read_text()) for f in folders]
        assert manifests[0]["environment_config"] == manifests[1]["environment_config"]
        assert manifests[0]["adapter"] is None and manifests[1]["adapter"]
        assert all(m["setup_ticks"] == 0 and m["rollout_max_sim_seconds"] == 10 for m in manifests)
        assert first[0]["prompt"] == first[1]["prompt"]
        assert first[0]["image_sha256"] == first[1]["image_sha256"]
        matched.append({"seed": seed, "initial_prompt_image_and_environment_identical": True})
    return {
        "runs": summaries,
        "matched_conditions": matched,
        "no_teacher_control_substitution": True,
        "inference_latency_not_charged_to_simulation": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(audit(args.runs))
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "runs": len(report["runs"]),
                "frames": sum(r["checked_original_mosaics_and_prompts"] for r in report["runs"]),
                "controls": sum(r["checked_decoded_controls"] for r in report["runs"]),
            }
        )
    )
