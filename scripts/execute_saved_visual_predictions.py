"""Execute saved visual-probe predictions in the exact source scene; no new model calls."""

import argparse
import asyncio
import hashlib
import io
import json
from pathlib import Path

import numpy as np

from uavlab.adapters.gym.deterministic_env import DeterministicEnv, Landmark
from uavlab.contracts import MissionSpec, TaskFamily
from uavlab.core.frame_store import global_store
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.reasoning.aerovla import make_dual_view_mosaic
from uavlab.training.direct_vla_fixture import context, student_state
from uavlab.training.direct_vla_frd import action_from_target, parse_target
from uavlab.training.visual_yaw_fixture import visible_bearing


def png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


async def run(args):
    args.out.mkdir(parents=True, exist_ok=False)
    model = json.loads(args.report.read_text())
    assert model["status"] == "complete"
    rows = [json.loads(s) for s in (args.data / "index.jsonl").read_text().splitlines()]
    source = {f"visible_yaw_s{r['seed']}_l{r['layout']}_{r['instruction_colour']}": r for r in rows}
    results = []
    for prediction in model["after"]:
        if prediction["task_group"] != "visual":
            continue
        identity = prediction["decision_id"]
        r = source[identity]
        assert r["split"] == "val" and r["seed"] in (1410, 1415)
        mission = MissionSpec(
            mission_id=identity,
            instruction=r["instruction"],
            task_family=TaskFamily.SEMANTIC_GOAL_NAV,
        )
        env = DeterministicEnv(
            scene="empty",
            n_obstacles=0,
            distractors=0,
            render=True,
            render_down=True,
            render_depth=False,
            image_size=224,
            allow_privileged=False,
            coarse_goal_direction=False,
        )
        await env.reset(mission, r["seed"])
        env.vehicle.yaw = r["state"]["yaw_enu_rad"]
        env.landmarks = [
            Landmark(position=np.array(x["position"]), label=x["label"], color=tuple(x["colour"]))
            for x in r["scene_audit_only"]
        ]
        env._last_hits = ()
        obs = await env.observe()
        assert student_state(obs) == r["state"]
        before = make_dual_view_mosaic(
            global_store().get(obs.rgb.uri), global_store().get(obs.rgb_down.uri), 224
        )
        assert png(before) == (args.data / r["images"]["mosaic"]).read_bytes()
        folder = args.out / identity
        folder.mkdir()
        (folder / "before.png").write_bytes(png(before))
        record = dict(
            id=identity,
            seed=r["seed"],
            instruction=r["instruction"],
            prediction=prediction,
            source_image_sha256=hashlib.sha256(png(before)).hexdigest(),
            controls=[],
            state_before=student_state(obs),
            data_row=r,
        )
        if not prediction["valid"]:
            record["outcome"] = "invalid_output_no_execution"
            results.append(record)
            await env.close()
            continue
        target = parse_target(prediction["raw"])
        action = action_from_target(target, obs.yaw_rad, duration_s=0.2)
        controller = MockVelocityController()
        controller.reset(mission, r["seed"])
        for _tick in range(4):
            obs = await env.observe()
            command = controller.from_action(action, context(mission, obs, identity), identity)
            record["controls"].append(
                dict(state=student_state(obs), command=command.model_dump(mode="json"))
            )
            await env.step(command, 50_000_000)
        obs = await env.observe()
        after = make_dual_view_mosaic(
            global_store().get(obs.rgb.uri), global_store().get(obs.rgb_down.uri), 224
        )
        (folder / "after.png").write_bytes(png(after))
        before_error, _ = visible_bearing(
            before, r["instruction_colour"], obs.intrinsics.cx, obs.intrinsics.fx
        )
        try:
            after_error, _ = visible_bearing(
                after, r["instruction_colour"], obs.intrinsics.cx, obs.intrinsics.fx
            )
        except ValueError:
            after_error = None
        record.update(
            state_after=student_state(obs),
            bearing_before=before_error,
            bearing_after=after_error,
            visible_error_reduced=after_error is not None and abs(after_error) < abs(before_error),
            translation_m=float(
                np.linalg.norm(np.array(obs.position.as_tuple()) - r["state"]["position_enu_m"])
            ),
            after_image_sha256=hashlib.sha256(png(after)).hexdigest(),
            outcome="saved_prediction_executed",
        )
        results.append(record)
        await env.close()
    assert len(results) == 16
    report = dict(
        model=model["model"],
        source_report=str(args.report),
        new_model_calls=0,
        segments=results,
        source_pixels_verified=16,
        executed_controls=sum(len(r["controls"]) for r in results),
        visual_error_reduced=sum(r.get("visible_error_reduced", False) for r in results),
        invalid=sum(r["outcome"] == "invalid_output_no_execution" for r in results),
        limits=(
            "0.2s execution diagnostic of saved final validation predictions,"
            "not a new closed-loop visual navigation evaluation"
        ),
    )
    (args.out / "execution.json").write_text(json.dumps(report, indent=2))
    print({k: v for k, v in report.items() if k != "segments"})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    asyncio.run(run(p.parse_args()))
