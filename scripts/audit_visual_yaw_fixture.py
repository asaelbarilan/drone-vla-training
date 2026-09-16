"""Independent source-image, label and full state/control replay audit for visible pairs."""

import argparse
import asyncio
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.adapters.gym.deterministic_env import DeterministicEnv, Landmark
from uavlab.contracts import ControlCommand, MissionSpec, TaskFamily
from uavlab.core.frame_store import global_store
from uavlab.plugins.reasoning.aerovla import make_dual_view_mosaic
from uavlab.training.direct_vla_fixture import student_state
from uavlab.training.direct_vla_frd import CONTRACT_ID, student_prompt


def png(image):
    b = io.BytesIO()
    image.save(b, format="PNG")
    return b.getvalue()


async def audit(root):
    rows = [json.loads(s) for s in (root / "index.jsonl").read_text().splitlines()]
    assert len(rows) == 64
    states = frames = controls = 0
    images = {}
    for r in rows:
        seed = r["seed"]
        assert 1410 <= seed <= 1417
        assert r["contract"] == CONTRACT_ID
        assert r["split"] == ("val" if seed % 5 == 0 else "train")
        assert r["prompt"] == student_prompt(r["instruction"], r["state"])
        for name, path in r["images"].items():
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == r["image_sha256"][name]
        mosaic = Image.open(root / r["images"]["mosaic"]).convert("RGB")
        assert png(
            make_dual_view_mosaic(
                Image.open(root / r["images"]["front"]), Image.open(root / r["images"]["down"]), 224
            )
        ) == png(mosaic)
        # Independent pixel-centroid computation, not a call back into the teacher.
        pixels = np.asarray(mosaic)[:112].astype(float)
        c = r["instruction_colour"]
        chosen = 0 if c == "red" else 2
        others = [i for i in range(3) if i != chosen]
        mask = (
            (pixels[:, :, chosen] > 100)
            & (pixels[:, :, chosen] > 1.8 * pixels[:, :, others[0]])
            & (pixels[:, :, chosen] > 1.8 * pixels[:, :, others[1]])
        )
        ys, xs = np.where(mask)
        assert len(xs) >= 12 and xs.min() >= 5 and xs.max() <= 218
        angle = np.arctan2(xs.mean() - r["intrinsics"]["cx"], r["intrinsics"]["fx"])
        expected_bin = round((float(angle) * 1.5 + 1.5) / 3 * 64)
        assert r["target"] == dict(
            forward_bin=32, right_bin=32, down_bin=32, yaw_cw_bin=expected_bin, stop=False
        )
        mission = MissionSpec(
            mission_id=f"visible-yaw-{seed}-{r['layout']}-{c}",
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
        await env.reset(mission, seed)
        env.vehicle.yaw = r["state"]["yaw_enu_rad"]
        env.landmarks = [
            Landmark(position=np.array(x["position"]), label=x["label"], color=tuple(x["colour"]))
            for x in r["scene_audit_only"]
        ]
        env._last_hits = ()
        for i, tick in enumerate(r["controls"]):
            obs = await env.observe()
            assert student_state(obs) == tick["state"]
            states += 1
            assert obs.t_sim_ns == tick["t_sim_ns"] == i * 50_000_000
            if i == 0:
                assert student_state(obs) == r["state"]
                for name, image in [
                    ("front", global_store().get(obs.rgb.uri)),
                    ("down", global_store().get(obs.rgb_down.uri)),
                ]:
                    assert png(image) == (root / r["images"][name]).read_bytes()
                    frames += 1
            cmd = ControlCommand.model_validate(tick["command"])
            assert cmd.velocity.as_tuple() == (0.0, 0.0, 0.0)
            assert cmd.yaw_rate_rps == -(r["target"]["yaw_cw_bin"] - 32) * 3 / 64
            assert cmd.t_sim_ns == obs.t_sim_ns
            assert cmd.expires_t_sim_ns == obs.t_sim_ns + 200_000_000
            await env.step(cmd, 50_000_000)
            controls += 1
        obs = await env.observe()
        assert student_state(obs) == r["after_state"]
        states += 1
        after = make_dual_view_mosaic(
            global_store().get(obs.rgb.uri), global_store().get(obs.rgb_down.uri), 224
        )
        assert png(after) == (root / r["after_image"]).read_bytes()
        frames += 1
        assert abs(r["after_bearing_cw_rad"]) < abs(angle)
        assert obs.position.as_tuple() == tuple(r["state"]["position_enu_m"])
        images.setdefault(r["image_sha256"]["mosaic"], set()).add(r["split"])
        await env.close()
    assert all(len(x) == 1 for x in images.values())
    pair_checks = 0
    for r in rows:
        other = next(
            x
            for x in rows
            if x["seed"] == r["seed"]
            and x["layout"] == r["layout"]
            and x["instruction_colour"] != r["instruction_colour"]
        )
        assert r["image_sha256"] == other["image_sha256"]
        assert (r["target"]["yaw_cw_bin"] - 32) * (other["target"]["yaw_cw_bin"] - 32) < 0
        swapped = next(
            x
            for x in rows
            if x["seed"] == r["seed"]
            and x["layout"] == (r["layout"] ^ 1)
            and x["instruction_colour"] == r["instruction_colour"]
        )
        assert (r["target"]["yaw_cw_bin"] - 32) * (swapped["target"]["yaw_cw_bin"] - 32) < 0
        pair_checks += 1
    return dict(
        passed=True,
        rows=len(rows),
        states=states,
        source_and_after_frames=frames,
        controls=controls,
        paired_checks=pair_checks,
        cross_split_duplicate_images=0,
        index_sha256=hashlib.sha256((root / "index.jsonl").read_bytes()).hexdigest(),
        limits="Teacher-data dependence only; no learned visual dependence demonstrated",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    report = asyncio.run(audit(a.data))
    a.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
