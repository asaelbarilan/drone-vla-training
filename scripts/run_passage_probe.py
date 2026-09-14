"""Run frozen six-call saved-image diagnostic once; evaluate without model retries."""

import asyncio
import base64
import hashlib
import json
import math
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.contracts import MemorySnapshot, MissionSpec, ObservationPacket, PerceptionState
from uavlab.core.camera import Camera
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.frame_store import global_store
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult
from uavlab.plugins.reasoning.onfly import OnFlyDecisionAgent

OUT = Path("reports/passage_choice_20260914")


class Saved:
    def __init__(self, answer):
        self.answer = answer

    async def invoke(self, request):
        return InferenceResult(payload=json.dumps(self.answer))


async def evaluate(freeze):
    rows = []
    for case in freeze["cases"]:
        for variant in freeze["variants"]:
            record = json.loads((OUT / f"{case['id']}_{variant}.json").read_text(encoding="utf-8"))
            row = dict(case=case["id"], variant=variant)
            try:
                answer = json.loads(record["reply"]["message"]["content"])
                row["answer"] = answer
                assert set(answer) == {"evidence", "kind", "u", "v"}
                assert (
                    answer["kind"]
                    in freeze["variants"][variant]["schema"]["properties"]["kind"]["enum"]
                )
                assert all(type(answer[k]) is int and 0 <= answer[k] <= 999 for k in ("u", "v"))
                if answer["kind"] == "hold":
                    row.update(
                        waypoint=None,
                        status="abstained",
                        note="No movement point; hold is probe-only",
                    )
                else:
                    obs = ObservationPacket.model_validate(case["observation"])
                    img = Image.open(OUT / (case["id"] + ".png")).convert("RGB")
                    global_store().put(obs.rgb.uri, img)
                    global_store().put(obs.depth.uri, np.load(OUT / (case["id"] + ".npz"))["depth"])
                    mission = MissionSpec(
                        mission_id="saved-passage",
                        instruction="fly to the red tower and stop there",
                        task_family="long_horizon_nav",
                    )
                    policy = OnFlyDecisionAgent(**freeze["policy"])
                    policy.reset(mission, 1061)
                    services = RuntimeServices(
                        clock=SimClock(),
                        log=EventLog("saved-lift"),
                        feature_cache=FeatureCache(),
                        inference=Saved(answer),
                        episode_id="saved-lift",
                    )
                    bind(policy, services)
                    ctx = DecisionContext(
                        mission=mission,
                        observation=obs,
                        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
                        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
                        t_sim_ns=obs.t_sim_ns,
                        t_wall_ns=obs.t_wall_ns,
                        episode_id="saved-lift",
                    )
                    decision = await policy.decide(ctx)
                    goal = decision.payload.target
                    origin = np.array([obs.position.x, obs.position.y, obs.position.z])
                    endpoint = np.array([goal.x, goal.y, goal.z])
                    length = float(np.linalg.norm(endpoint - origin))
                    n = max(2, math.ceil(length / 0.05) + 1)
                    samples = origin + (endpoint - origin) * np.linspace(0, 1, n)[:, None]
                    distances = []
                    for o in case["obstacles"]:
                        delta = np.abs(samples - np.array(o["center"])) - np.array(o["half"])
                        distances.append(
                            np.linalg.norm(np.maximum(delta, 0), axis=1)
                            + np.minimum(np.max(delta, axis=1), 0)
                        )
                    clearance = float(np.min(distances))
                    bound = clearance - length / (2 * (n - 1))
                    u, v = answer["u"] * 223 / 999, answer["v"] * 223 / 999
                    intr = obs.intrinsics
                    camera = Camera(
                        width=intr.width,
                        height=intr.height,
                        fov_deg=math.degrees(2 * math.atan(intr.width / (2 * intr.fx))),
                        pitch_rad=-0.15,
                    )
                    pixel, _ = camera.project(endpoint[None, :], origin, obs.yaw_rad)
                    row.update(
                        status="point",
                        pixel=[u, v],
                        pixel_rgb=list(img.getpixel((round(u), round(v)))),
                        waypoint=goal.model_dump(mode="json"),
                        lift_provenance=decision.provenance,
                        straight_segment_sampled_clearance_m=clearance,
                        straight_segment_clearance_lower_bound_m=bound,
                        meets_0_6m_straight_clearance=bound >= 0.6,
                        meets_1_2m_straight_clearance=bound >= 1.2,
                        roundtrip_pixel_error=float(np.linalg.norm(pixel[0] - [u, v]))
                        if length > 1e-6
                        else None,
                    )
                    services.log.close()
            except Exception as exc:
                row.update(status="invalid", error=str(exc))
            rows.append(row)
    (OUT / "RESULTS.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2))


async def main():
    f = json.loads((OUT / "FREEZE.json").read_text(encoding="utf-8"))
    p = f["inference"]
    if "--evaluate-only" not in sys.argv:
        paths = [OUT / f"{c['id']}_{v}.json" for c in f["cases"] for v in f["variants"]]
        assert not any(path.exists() for path in paths), (
            "Refuse repeated model calls; use --evaluate-only"
        )
        with urllib.request.urlopen(p["host"] + "/api/tags", timeout=10) as r:
            tags = json.load(r)
        assert (
            next(t for t in tags["models"] if t["name"] == p["model_id"])["digest"]
            == p["expected_digest"]
        )
        for case in f["cases"]:
            img = (OUT / (case["id"] + ".png")).read_bytes()
            assert hashlib.sha256(img).hexdigest() == case["source_sha256"]
            for variant, config in f["variants"].items():
                body = dict(
                    model=p["model_id"],
                    messages=[
                        dict(
                            role="user",
                            content=config["prompt"],
                            images=[base64.b64encode(img).decode()],
                        )
                    ],
                    stream=False,
                    think=p["think"],
                    keep_alive=p["keep_alive"],
                    options=dict(
                        temperature=p["temperature"],
                        seed=p["sampling_seed"],
                        num_ctx=p["num_ctx"],
                        num_predict=p["num_predict"],
                    ),
                    format=config["schema"],
                )
                request = urllib.request.Request(
                    p["host"] + "/api/chat",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=180) as r:
                    reply = json.load(r)
                record = dict(
                    case=case["id"],
                    variant=variant,
                    source_sha256=case["source_sha256"],
                    prompt=config["prompt"],
                    schema=config["schema"],
                    options=body["options"],
                    reply=reply,
                )
                (OUT / f"{case['id']}_{variant}.json").write_text(
                    json.dumps(record, indent=2), encoding="utf-8"
                )
                print(case["id"], variant, reply["message"]["content"], flush=True)
    await evaluate(f)


if __name__ == "__main__":
    asyncio.run(main())
