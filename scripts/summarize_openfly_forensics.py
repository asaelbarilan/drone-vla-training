# ruff: noqa: E501
"""Reproduce D146 decoding diagnostics; never replace the frozen D145 results."""

import collections
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from build_openfly_same_panel import CODEBOOK

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_forensics_20260918"
OLD = ROOT / "reports/vla_openfly_same_panel_20260918"
rows = list(map(json.loads, (OLD / "inputs.jsonl").read_text().splitlines()))
cfg = json.loads(Path("D:/drone_vla_pilot/models/openfly-agent-7b/config.json").read_text())
configs = {
    "baseline": OLD / "probe.json",
    "training_prompt": Path(
        "D:/drone_vla_pilot/runs/openfly_forensic_prompt_20260918_b/probe.json"
    ),
    "training_history_pooling": Path(
        "D:/drone_vla_pilot/runs/openfly_forensic_pooling_20260918/probe.json"
    ),
}
vocab = cfg["text_config"]["vocab_size"] - cfg["pad_to_multiple_of"]
bins = np.linspace(-1, 1, cfg["n_action_bins"])
centers = (bins[:-1] + bins[1:]) / 2
results = {}
for name, path in configs.items():
    probe = json.loads(path.read_text())
    assert len(probe["outputs"]) == 72
    assert (
        probe["evaluation_data_sha256"]
        == hashlib.sha256((OLD / "inputs.jsonl").read_bytes()).hexdigest()
    )
    assert not probe["loading"]["missing_keys"] and not probe["loading"]["unexpected_keys"]
    for row, o in zip(rows, probe["outputs"], strict=True):
        assert row["id"] == o["decision_id"] and row["image_sha256"] == o["image_sha256"]
    if name != "baseline":
        assert all(o["generated_token_count"] == 8 for o in probe["outputs"])
        (OUT / (name + "_probe.json")).write_text(json.dumps(probe, indent=2))
    for key in ["vlnv1", "vln_norm", "vlnv11"]:
        stats = cfg["norm_stats"][key]["action"]
        pred = []
        for o in probe["outputs"]:
            tokens = np.array(o["action_token_ids"])
            z = centers[np.clip(vocab - tokens - 1, 0, len(centers) - 1)]
            action = np.where(
                stats["mask"],
                0.5 * (z + 1) * (np.array(stats["q99"]) - stats["q01"]) + stats["q01"],
                z,
            )
            if key == "vlnv1":
                assert np.allclose(action, o["raw_action"], atol=1e-6)
            vector = np.rint(action).astype(int).tolist()
            pred.append(
                CODEBOOK.index(vector)
                if vector in CODEBOOK and o["tokens_in_action_range"]
                else None
            )
        results[name + ":" + key] = dict(
            direction=sum(
                (1 if a in (8, 9) else a) == r["action_id"] for a, r in zip(pred, rows, strict=True)
            ),
            exact=sum(a == r["action_id"] for a, r in zip(pred, rows, strict=True)),
            valid=sum(a is not None for a in pred),
            n=72,
            action_counts=dict(collections.Counter(str(a) for a in pred)),
            predictions=pred,
        )
legacy = json.loads((OLD / "predictions.json").read_text())
horizontal = {
    name: dict(n=48, correct=sum(p["direction_correct"] for p in ps if p["target"] < 4))
    for name, ps in legacy.items()
}
report = dict(
    status="complete",
    results=results,
    horizontal_only_legacy=horizontal,
    warning="Normalization sensitivity is diagnostic, not a corrected leaderboard. No source-verified environment-to-key mapping was found. All vertical outputs under vlnv1 are identically zero.",
    labels=json.loads((OUT / "label_audit.json").read_text()),
)
(OUT / "results.json").write_text(json.dumps(report, indent=2))
print(
    json.dumps(
        {
            k: {x: y for x, y in v.items() if x not in ("predictions", "action_counts")}
            for k, v in results.items()
        }
    )
)
print(json.dumps(horizontal))

view = ROOT / "reports/vla_dataset_review_20260916"
body = "".join(
    "<tr><td>"
    + html.escape(k)
    + "</td><td>"
    + str(v["direction"])
    + "/72</td><td>"
    + str(v["exact"])
    + "/72</td><td>"
    + str(v["valid"])
    + "/72</td></tr>"
    for k, v in results.items()
)
page = (
    '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>OpenFly comparison investigation</title><style>body{background:#102033;color:#edf3fc;font:17px system-ui;max-width:1100px;margin:30px auto;padding:0 20px;line-height:1.55}a{color:#80caff}section{background:#1a3049;padding:20px;margin:20px 0;border-radius:10px}.warning{color:#ffcd88}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:8px;border-bottom:1px solid #53657a}.scroll{overflow-x:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>OpenFly comparison: investigation</h1><section class="warning"><b>The previous table is not a validated model ranking.</b><p>The vlnv1 decoder forces both vertical outputs to zero. That makes 24 of 72 targets unreachable. This is a confirmed evaluation limitation, not proof that our models match the released model.</p></section><section><h2>Data checks</h2><p>72/72 source image identities match. 60/60 movement labels agree with the next recorded pose. 12/12 STOP labels agree with the final source annotation. All64 frames also present in compressed annotations agree in direction.</p><p>This checks labels and alignment, not the correctness of every route instruction or the entire dataset.</p></section><section><h2>Controlled diagnostics</h2><p>Same frozen72 examples, images and 4-bit weights. Training prompt and history pooling are separate one-factor interventions. Alternative normalization rows reuse saved tokens; they are sensitivity checks, not accepted corrected scores.</p><div class="scroll"><table><tr><th>Interface : normalization</th><th>Direction</th><th>Exact primitive</th><th>Valid vector</th></tr>'
    + body
    + '</table></div><p>vlnv1: both vertical ranges zero. vln_norm: down range zero and forward maximum5. vlnv11: vertical-capable profile; its applicability to this checkpoint/context is unverified. Picking the highest score would not establish the correct interface.</p></section><section><h2>What next</h2><p>Establish the checkpoint normalization and causal history contract before more training. Add an official annotation-boundary macro-action evaluation and then compare actual closed-loop flights. The current raw atomic panel remains preserved as a diagnostic.</p><p>Published flight success within20m is a different metric from next-action agreement. Full-precision versus4-bit behavior remains untested.</p><a href="https://arxiv.org/html/2502.18041v6">Official paper</a></section><details><summary>Full investigation and source caveats</summary><pre>'
    + html.escape((OUT / "REPORT.md").read_text())
    + '</pre></details><p><a href="openfly_same_panel.html">Preserved comparison and raw outputs</a></p></html>'
)
(view / "openfly_forensics.html").write_text(page, encoding="utf-8")
