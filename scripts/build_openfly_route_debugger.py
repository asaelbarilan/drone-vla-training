"""Build the complete-route debugger from frozen inputs and completed outputs."""

import collections
import hashlib
import json
import math
from pathlib import Path

from PIL import Image

from uavlab.training.openfly_codec import OpenFlyCodec
from uavlab.training.openfly_history import direction

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_routes_20260919"
VIEW = ROOT / "reports/vla_dataset_review_20260916"
NAMES = {
    0: "STOP",
    1: "Forward 3 m",
    2: "Left turn 30 deg",
    3: "Right turn 30 deg",
    4: "Up 3 m",
    5: "Down 3 m",
    8: "Forward 6 m",
    9: "Forward 9 m",
}


def summarize(rows, predictions):
    out = {}
    for variant in sorted({r["variant"] for r in rows}):
        selected = [r for r in rows if r["variant"] == variant]
        p = [predictions[r["id"]]["strict_decoded"]["action_id"] for r in selected]
        out[variant] = dict(
            n=len(selected),
            valid=sum(a is not None for a in p),
            direction=sum(
                direction(a) == r["direction_id"] for a, r in zip(p, selected, strict=False)
            ),
            exact=sum(a == r["action_id"] for a, r in zip(p, selected, strict=False)),
            always_forward=sum(r["direction_id"] == 1 for r in selected),
            predicted_counts=dict(collections.Counter(str(a) for a in p)),
            target_counts=dict(collections.Counter(str(r["direction_id"]) for r in selected)),
        )
    return out


def main():
    rows = [json.loads(x) for x in (OUT / "all_inputs.jsonl").read_text().splitlines()]
    probe = json.loads(
        Path("D:/drone_vla_pilot/runs/openfly_routes_20260919_b/probe.json").read_text()
    )
    preds = {p["decision_id"]: p for p in probe["outputs"]}
    assert len(rows) == len(preds) == 274
    assert set(preds) == {r["id"] for r in rows}
    assert all(preds[r["id"]]["image_sha256"] == r["image_sha256"] for r in rows)
    (OUT / "openfly_predictions.json").write_text(json.dumps(probe, indent=2))
    qwen = json.loads((OUT / "qwen_routes.json").read_text())
    qp = {p["id"]: p for p in qwen["outputs"]}
    assert len(qp) == 43
    routes = json.loads((OUT / "routes.json").read_text())
    summary = dict(
        route_controls=summarize(rows[:172], preds),
        routes={},
        rlds={},
        elapsed_s=probe["elapsed_s"],
    )
    for route in routes:
        chosen = [r for r in rows[:172] if r["trajectory"] == route["trajectory"]]
        stats = summarize(chosen, preds)
        prior = [r for r in chosen if r["variant"] == "prior_adjacent"]
        stats["qwen"] = dict(
            n=len(prior),
            valid=sum(qp[r["id"]]["action_id"] is not None for r in prior),
            direction=sum(qp[r["id"]]["action_id"] == r["direction_id"] for r in prior),
            always_forward=sum(r["direction_id"] == 1 for r in prior),
        )
        summary["routes"][route["category"]] = stats
        for d in route["decisions"]:
            d["predictions"] = {}
            for variant in [
                "prior_adjacent",
                "native_resize",
                "transition_history",
                "training_interface",
            ]:
                key = variant + ":" + d["id"]
                d["predictions"][variant] = preds[key]
            d["predictions"]["qwen"] = dict(
                action_id=qp["prior_adjacent:" + d["id"]]["action_id"],
                raw=qp["prior_adjacent:" + d["id"]]["raw"],
            )
            d["goal_distance_source_units"] = math.dist(
                route["frames"][d["frame_index"]]["pos"][:3], route["frames"][-1]["pos"][:3]
            )
        route["kind"] = "raw"
    for subset in ["vlnv1", "vlnv11"]:
        source = [r for r in rows[172:] if r["norm_key"] == subset]
        summary["rlds"][subset] = dict(
            all_steps=summarize(source, preds),
            pipeline_kept=summarize(
                [r for r in source if r["training_pipeline_keeps_step"]], preds
            ),
        )
        record = json.loads((OUT / (subset + "_record.json")).read_text())
        f = record["fields"]
        frames = []
        decisions = []
        for i, item in enumerate(f["steps/observation/image_1"]):
            preview = VIEW / "route_assets" / subset / f"{i:04}.jpg"
            preview.parent.mkdir(parents=True, exist_ok=True)
            Image.open(item["path"]).convert("RGB").save(preview, quality=90)
            frames.append(
                dict(
                    index=i,
                    image=item["path"],
                    sha256=item["sha256"],
                    preview=preview.relative_to(VIEW).as_posix(),
                    pos=None,
                    yaw=None,
                )
            )
            r = next(
                x for x in source if x["variant"] == "rlds_stored_raw" and x["frame_index"] == i
            )
            decisions.append(
                dict(
                    id=r["source_id"],
                    frame_index=i,
                    action_id=r["action_id"],
                    direction_id=r["direction_id"],
                    predictions={
                        v: preds[f"{v}:{subset}:{i}"]
                        for v in ["rlds_stored_raw", "rlds_stored_training", "rlds_causal_training"]
                    },
                    future_history_slots=r["future_history_slots"],
                )
            )
        routes.append(
            dict(
                category="packed_" + subset,
                trajectory=source[0]["trajectory"],
                instruction=f["steps/language_instruction"][0],
                kind="packed",
                frames=frames,
                decisions=decisions,
            )
        )
    # Explicitly show calibration sensitivity without choosing whichever scores best.
    config = json.loads(Path("D:/drone_vla_pilot/models/openfly-agent-7b/config.json").read_text())
    codec = OpenFlyCodec(config, "vlnv1")
    for p in preds.values():
        p["horizontal_profile_diagnostic"] = codec.decode(p["action_token_ids"])
    summary["calibration"] = json.loads((OUT / "calibration_sensitivity.json").read_text())
    for route in routes:
        if route["kind"] == "raw":
            for d in route["decisions"]:
                original = d["predictions"]["prior_adjacent"]
                d["predictions"]["horizontal_decode_diagnostic"] = dict(
                    original,
                    strict_decoded=original["horizontal_profile_diagnostic"],
                    norm_key="vlnv1 (counterfactual; route calibration unverified)",
                )
        for d in route["decisions"]:
            for variant, p in d["predictions"].items():
                if variant == "qwen":
                    continue
                p["actual_input_indices"] = [
                    [f["index"] for f in route["frames"] if f["sha256"] == sha]
                    for sha in p["image_sha256"]
                ]
                p["input_previews"] = []
                for path in p["images"]:
                    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
                    target = VIEW / "route_assets" / "inputs" / (sha + ".jpg")
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        im = Image.open(path).convert("RGB")
                        im.thumbnail((512, 288))
                        im.save(target, quality=85)
                    p["input_previews"].append(target.relative_to(VIEW).as_posix())
    summary["rlds_future_history"] = json.loads((OUT / "rlds_audit.json").read_text())
    summary["paper"] = dict(
        seen_sr=33.2,
        unseen_sr=10.7,
        seen_osr=63.5,
        unseen_osr=48.9,
        history_sr=12.7,
        full_sr=33.2,
        goal_radius_m=20,
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    data = dict(routes=routes, summary=summary, action_names=NAMES)
    (VIEW / "openfly_routes.json").write_text(json.dumps(data))
    template = (ROOT / "scripts/templates/openfly_routes.html").read_text(encoding="utf-8")
    (VIEW / "openfly_routes.html").write_text(template, encoding="utf-8")
    print(
        json.dumps(
            {"routes": len(routes), "model_predictions": len(preds) + len(qp), "status": "built"}
        )
    )


if __name__ == "__main__":
    main()
