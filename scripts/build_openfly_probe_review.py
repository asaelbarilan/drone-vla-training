# ruff: noqa: E501
"""Compare native OpenFly visual directions with saved Smol development probes."""

import base64
import html
import json
import shutil
import statistics
from pathlib import Path

OUT = Path("reports/vla_openfly_20260917")
VIEW = Path("reports/vla_dataset_review_20260916/openfly_comparison.html")
RUNS = Path("D:/drone_vla_pilot/runs")
rows = {
    r["decision_id"]: r
    for r in map(
        json.loads,
        Path("D:/drone_vla_pilot/data/local_expanded_20260917_v4/index.jsonl")
        .read_text()
        .splitlines(),
    )
}
reports = {}
for key, folder in (
    ("model_card", "openfly_visual16_20260917"),
    ("training", "openfly_training_prompt16_20260917"),
):
    reports[key] = json.loads((RUNS / folder / "probe.json").read_text())
    shutil.copyfile(RUNS / folder / "probe.json", OUT / f"{key}_probe.json")


def direction(a):
    a = tuple(a)
    if a == (1, 0, 0, 0, 0, 0, 0, 0):
        return "STOP"
    if a == (0, 0, 15, 0, 0, 0, 0, 0):
        return "left"
    if a == (0, 0, 0, 15, 0, 0, 0, 0):
        return "right"
    return "other / unexecuted"


metrics = {}
for key, report in reports.items():
    expected = [
        "right" if rows[r["decision_id"]]["target"]["yaw_cw_bin"] > 32 else "left"
        for r in report["outputs"]
    ]
    predicted = [direction(r["rounded_action"]) for r in report["outputs"]]
    assert len(expected) == 16
    metrics[key] = dict(
        correct_directions=sum(a == b for a, b in zip(expected, predicted, strict=False)),
        n=16,
        stops=predicted.count("STOP"),
        valid_action_tokens=sum(r["tokens_in_action_range"] for r in report["outputs"]),
        median_latency_s=statistics.median(r["latency_s"] for r in report["outputs"]),
        peak_allocated_bytes=report["peak_allocated_bytes"],
    )
summary = dict(
    metrics=metrics,
    limits="Development transfer diagnostic only; no OpenFly flight execution, no native benchmark reproduction. Front image vs Smol dual-view mosaic; 4-bit pretrained OpenFly vs locally fine-tuned BF16 Smol; do not rank overall model quality.",
    action_units="Native 8-vector, not vx/vy/vz/yaw. Left/right semantic direction only; official evaluation code maps turn token15 to30deg and differs from encoded units. Full execution adapter pending.",
)
(OUT / "summary.json").write_text(json.dumps(summary, indent=2))
esc = html.escape
body = [
    "<!doctype html><meta charset='utf-8'><title>OpenFly local comparison</title>",
    "<style>body{background:#101824;color:#e2ebf5;font:16px system-ui;max-width:1100px;margin:30px auto;padding:20px}article{border:1px solid #486079;padding:18px;margin:16px 0}img{width:224px}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#73d9ec}table{border-collapse:collapse}td,th{padding:12px;border:1px solid #486079}</style>",
    "<h1>OpenFly: initial local comparison</h1><p>Downloaded and verified; native 4-bit inference on this laptop. No training.</p>",
    "<p>Same 16 existing visual development cases. OpenFly uses the front image and three repeated initial history frames. Smol used a front/down mosaic. This tests transfer and integration, not general flight capability.</p>",
    "<table><tr><th>Condition</th><th>Correct direction</th><th>STOPs</th></tr>",
    "<tr><td>Smol256 original data</td><td>8/16</td><td>0/16</td></tr><tr><td>Smol256 expanded data</td><td>8/16</td><td>0/16</td></tr>",
]
for key, metric in metrics.items():
    body.append(
        f"<tr><td>OpenFly {key} prompt</td><td>{metric['correct_directions']}/16</td><td>{metric['stops']}/16</td></tr>"
    )
body += [
    "</table><p>Training-template OpenFly always turns right. Model-card prompt always STOPs. The input template materially changes behavior; neither establishes instruction grounding.</p>",
    f"<p>{esc(summary['limits'])}</p><p>{esc(summary['action_units'])}</p>",
    "<p><a href='balanced_control_flights.html#run=smol256_mixed_frd_trained_s1400'>Original Smol flights</a> | <a href='balanced_expanded_flights.html#run=smol256_mixed_frd_trained_s1400'>Expanded Smol flights</a></p>",
]
card = {r["decision_id"]: r for r in reports["model_card"]["outputs"]}
for r in reports["training"]["outputs"]:
    row = rows[r["decision_id"]]
    target = "right" if row["target"]["yaw_cw_bin"] > 32 else "left"
    data = base64.b64encode(Path(r["image"]).read_bytes()).decode()
    body += [
        f"<article><h2>{esc(r['decision_id'])}</h2><img src='data:image/png;base64,{data}' alt='Exact OpenFly front image'><p>{esc(r['instruction'])}</p>",
        f"<p>Expected: {target}. OpenFly training template: {direction(r['rounded_action'])}. Model-card template: {direction(card[r['decision_id']]['rounded_action'])}.</p>",
        f"<details><summary>Exact prompt and native action evidence</summary><pre>{esc(json.dumps(r, indent=2))}</pre></details></article>",
    ]
VIEW.write_text("\n".join(body), encoding="utf-8")
print(json.dumps(summary, indent=2))
