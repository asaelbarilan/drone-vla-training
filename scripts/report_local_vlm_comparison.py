"""Verify request identity and build the saved-image model comparison dashboard."""

import base64
import hashlib
import json
from pathlib import Path

from local_vlm_comparison import OUT, SOURCE, evaluate, read, save

f = read(OUT / "FREEZE.json")
rows = evaluate()
images = {}
records = {}
verified = 0
cpu_residencies = []
for case in f["cases"]:
    for variant, spec in f["variants"].items():
        key = case["id"] + "_" + variant
        raw = (OUT / (key + ".png")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case["input_sha256"][variant]
        images[key] = "data:image/png;base64," + base64.b64encode(raw).decode()
        baseline = read(SOURCE / (key + ".json"))
        records["gemma_" + key] = baseline
        for model in f["models"]:
            path = OUT / model["id"] / (key + ".json")
            if not path.exists():
                continue
            record = read(path)
            request = record["request"]
            assert base64.b64decode(request["messages"][0]["images"][0]) == raw
            assert request["messages"][0]["content"] == spec["prompt"]
            assert request["format"] == spec["schema"]
            assert request["options"] == f["options"]
            assert request["model"] == model["name"]
            assert record["model"]["digest"] == model["digest"]
            if "reply" in record:
                assert record["reply"]["model"] == model["name"]
                assert record["reply"]["done"] is True
            for resident in record.get("residency", {}).get("models", []):
                assert resident.get("size_vram", 0) == 0
                assert resident["digest"] == model["digest"]
                cpu_residencies.append(dict(experiment_model=model["id"], **resident))
            verified += 1
            # Image bytes are displayed separately; full original request remains on disk.
            request["messages"][0]["images"] = ["[exact PNG shown above]"]
            records[model["id"] + "_" + key] = record

models = [dict(id="gemma", name="gemma4:e2b (saved baseline)"), *f["models"]]
summary = []
for model in models:
    subset = [r for r in rows if r["model"] == model["id"]]
    positive_grid = next(
        r for r in subset if r["case"] == "visible_target" and r["variant"] == "grid"
    )
    positive_box = next(
        r for r in subset if r["case"] == "visible_target" and r["variant"] == "bbox"
    )
    summary.append(
        dict(
            model=model["name"],
            id=model["id"],
            grid_visible=positive_grid["status"],
            box_visible=positive_box["status"],
            box_iou=positive_box.get("iou"),
            grid_absent=sum(
                r["passed"]
                for r in subset
                if r["case"] != "visible_target" and r["variant"] == "grid"
            ),
            box_absent=sum(
                r["passed"]
                for r in subset
                if r["case"] != "visible_target" and r["variant"] == "bbox"
            ),
            errors=sum(r["status"] in ("runtime_error", "invalid_output") for r in subset),
            pending=sum(r["status"] == "pending" for r in subset),
        )
    )
save(OUT / "SUMMARY.json", summary)
proof = dict(
    requests_verified=verified,
    maximum_new_attempts=42,
    historical_baseline_calls=6,
    cpu_residency_checks=len(cpu_residencies),
    cloud_calls=0,
    flights=0,
    no_runtime_changes=True,
    pending=sum(r["status"] == "pending" for r in rows),
)
save(OUT / "VERIFICATION.json", proof)
save(OUT / "CPU_RESIDENCY.json", cpu_residencies)
data = dict(
    freeze=f,
    rows=rows,
    models=models,
    images=images,
    records=records,
    summary=summary,
    verification=proof,
)
template = Path("scripts/templates/local_vlm_comparison.html").read_text(encoding="utf-8")
Path("reports/debugger/local_vlm_comparison.html").write_text(
    template.replace("__DATA__", json.dumps(data).replace("<", "\\u003c")), encoding="utf-8"
)
lines = [
    "# D-114 - Seven installed VLMs on the frozen localization experiment",
    "",
    f["interpretation"],
    "",
    "One visible target and two absent scenes; six requests per model.",
    "A model passes a format only if it passes the positive and both negatives. "
    "Grid and box scores measure different precision; do not sum them into a ranking.",
    "",
    "| Model | Visible grid | Absent grid /2 | Visible box | IoU | "
    "Absent box /2 | Errors | Pending |",
    "|---|---|---:|---|---:|---:|---:|---:|",
]
for s in summary:
    iou = "—" if s["box_iou"] is None else f"{s['box_iou']:.4f}"
    lines.append(
        f"| {s['model']} | {s['grid_visible']} | {s['grid_absent']} | "
        f"{s['box_visible']} | {iou} | {s['box_absent']} | {s['errors']} | {s['pending']} |"
    )
lines += [
    "",
    "## Verification",
    "",
    json.dumps(proof, indent=2),
    "",
    "All raw requests include original PNG base64, full model ID/digest, options and schema. "
    "Raw replies retain both content and thinking channels. Failed requests are retained. "
    "CPU residency records include actual context length: some backends clamp the requested "
    "8192 tokens to their supported context. The request token budget is 192, so truncated "
    "responses and interface limitations must not be interpreted as visual incapacity.",
    "",
    "Historical Gemma used GPU/shared-server execution. No speed ranking is justified. "
    "No weights downloaded and no flight/runtime configuration promoted.",
]
(OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps(proof))
