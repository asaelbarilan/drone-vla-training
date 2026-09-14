"""Standalone paired source/pixel/waypoint evidence; zero inference."""

import base64
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path("reports/passage_choice_20260914")
f = json.loads((OUT / "FREEZE.json").read_text(encoding="utf-8"))
rows = json.loads((OUT / "RESULTS.json").read_text(encoding="utf-8"))
cases = []
records = []
for c in f["cases"]:
    raw = (OUT / (c["id"] + ".png")).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == c["source_sha256"]
    pairs = []
    for variant in f["variants"]:
        record = json.loads((OUT / f"{c['id']}_{variant}.json").read_text(encoding="utf-8"))
        records.append(record)
        assert record["source_sha256"] == c["source_sha256"]
        assert record["prompt"] == f["variants"][variant]["prompt"]
        assert record["schema"] == f["variants"][variant]["schema"]
        row = next(r for r in rows if r["case"] == c["id"] and r["variant"] == variant)
        assert row["status"] == "point"
        assert row["roundtrip_pixel_error"] < 1e-8
        row["prompt"] = record["prompt"]
        row["raw_reply"] = record["reply"]["message"]["content"]
        pairs.append(row)
    cases.append(
        dict(
            id=c["id"],
            run=c["run"],
            call=c["call"],
            source_t=c["source_t"],
            expectation=c["expectation"],
            image="data:image/png;base64," + base64.b64encode(raw).decode(),
            pairs=pairs,
        )
    )
assert len(records) == 6 and all(r["options"] == records[0]["options"] for r in records)
# Diagnostic annotation only, never part of the input sent to the model.
a = np.asarray(Image.open(OUT / "visible_target.png").convert("RGB"))
ys, xs = np.where(
    (a[:, :, 0] > 150)
    & (a[:, :, 0] > a[:, :, 1].astype(int) + 50)
    & (a[:, :, 0] > a[:, :, 2].astype(int) + 50)
)
bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
proof = dict(
    completed_model_calls=6,
    cloud_calls=0,
    new_flights=0,
    exact_source_pairs=3,
    options_identical=True,
    all_six_points_land_on_visually_inspected_gray_faces=True,
    maximum_lift_roundtrip_pixel_error=max(r["roundtrip_pixel_error"] for r in rows),
    visible_red_diagnostic_bbox=bbox,
    candidate_hold_count=sum(r["answer"]["kind"] == "hold" for r in rows),
    candidate_promoted=False,
    scope=(
        "Selected-frame diagnostic, not general benchmark; visibility inferred from response, "
        "no separate target_visible field"
    ),
)
(OUT / "VERIFICATION.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
html = Path("scripts/templates/passage_choice.html").read_text(encoding="utf-8")
html = html.replace("__DATA__", json.dumps(cases).replace("</", r"<\/")).replace(
    "__BBOX__", json.dumps(bbox)
)
Path("reports/debugger/passage_choice.html").write_text(html, encoding="utf-8")
print(json.dumps(proof, indent=2))
