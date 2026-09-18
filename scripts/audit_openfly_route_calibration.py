"""Same-token calibration sensitivity, never select a profile by score."""

import json
from pathlib import Path

from uavlab.training.openfly_codec import OpenFlyCodec
from uavlab.training.openfly_history import direction

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_routes_20260919"


def main():
    config = json.loads(Path("D:/drone_vla_pilot/models/openfly-agent-7b/config.json").read_text())
    codecs = {k: OpenFlyCodec(config, k) for k in ["vlnv1", "vlnv11"]}
    rows = {
        r["id"]: r for r in map(json.loads, (OUT / "all_inputs.jsonl").read_text().splitlines())
    }
    predictions = json.loads(
        Path("D:/drone_vla_pilot/runs/openfly_routes_20260919_b/probe.json").read_text()
    )["outputs"]
    result = {}
    examples = []
    for group in ["airsim_horizontal", "airsim_vertical", "gs_horizontal", "vlnv1", "vlnv11"]:
        selected = [
            p
            for p in predictions
            if (
                p["variant"] == "prior_adjacent"
                and rows[p["decision_id"]]["route_category"] == group
            )
            or (p["variant"] == "rlds_stored_raw" and p["norm_key"] == group)
        ]
        result[group] = {}
        for norm_key, codec in codecs.items():
            decoded = [codec.decode(p["action_token_ids"])["action_id"] for p in selected]
            result[group][norm_key] = dict(
                n=len(selected),
                valid=sum(a is not None for a in decoded),
                direction=sum(
                    direction(a) == rows[p["decision_id"]]["direction_id"]
                    for a, p in zip(decoded, selected, strict=True)
                ),
                exact=sum(
                    a == rows[p["decision_id"]]["action_id"]
                    for a, p in zip(decoded, selected, strict=True)
                ),
            )
        if group == "vlnv1":
            for p in selected:
                a = codecs["vlnv1"].decode(p["action_token_ids"])
                b = codecs["vlnv11"].decode(p["action_token_ids"])
                if a["action_id"] is not None and b["action_id"] is None:
                    examples.append(
                        dict(
                            id=p["decision_id"],
                            tokens=p["action_token_ids"],
                            source_matched=a,
                            wrong_vertical_profile=b,
                        )
                    )
    (OUT / "calibration_sensitivity.json").write_text(
        json.dumps(
            dict(
                groups=result,
                examples=examples,
                note=(
                    "Same saved tokens; no inference or score-based selection. "
                    "Exact source subset is known only for packed records. "
                    "Route profiles remain unproven."
                ),
            ),
            indent=2,
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
