# ruff: noqa: E501
"""D145 comparison on exact D144 OpenFly observations, with explicit action semantics."""

import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/vla_openfly_same_panel_20260918"
JOINT = ROOT / "reports/vla_joint_openfly_20260917"
VIEW = ROOT / "reports/vla_dataset_review_20260916"
RUN = Path("D:/drone_vla_pilot/runs/openfly_same_panel_20260918_a")
LABELS = [
    "STOP",
    "forward 3m",
    "left turn 30 degrees",
    "right turn 30 degrees",
    "up 3m",
    "down 3m",
    "left",
    "right",
    "forward 6m",
    "forward 9m",
]
# Released train/eval.py codebook. Its controller maps vertical value2 to a3m primitive.
CODEBOOK = [
    [1, 0, 0, 0, 0, 0, 0, 0],
    [0, 3, 0, 0, 0, 0, 0, 0],
    [0, 0, 15, 0, 0, 0, 0, 0],
    [0, 0, 0, 15, 0, 0, 0, 0],
    [0, 0, 0, 0, 2, 0, 0, 0],
    [0, 0, 0, 0, 0, 2, 0, 0],
    [0, 0, 0, 0, 0, 0, 5, 0],
    [0, 0, 0, 0, 0, 0, 0, 5],
    [0, 6, 0, 0, 0, 0, 0, 0],
    [0, 9, 0, 0, 0, 0, 0, 0],
]


def build():
    rows = list(map(json.loads, (REPORT / "inputs.jsonl").read_text().splitlines()))
    probe = json.loads((RUN / "probe.json").read_text())
    assert probe["status"] == "inference_complete" and probe["norm_key"] == "vlnv1"
    assert (
        probe["evaluation_data_sha256"]
        == hashlib.sha256((REPORT / "inputs.jsonl").read_bytes()).hexdigest()
    )
    assert len(rows) == len(probe["outputs"]) == 72
    assert not probe["loading"]["missing_keys"] and not probe["loading"]["unexpected_keys"]
    models = {}
    for name in ["smol256", "smol500", "qwen"]:
        r = json.loads((JOINT / f"{name}_training_report.json").read_text())
        assert r["status"] == "complete"
        predictions = [p for p in r["after"] if p["source"] == "openfly"]
        assert [p["id"] for p in predictions] == [r["id"] for r in rows]
        models[name] = [
            {"id": p["id"], "action_id": p["parsed"], "raw": p["raw"], "target": p["target"]}
            for p in predictions
        ]
    native = []
    for row, p in zip(rows, probe["outputs"], strict=True):
        assert p["decision_id"] == row["id"] and p["images"] == row["images"]
        assert p["image_sha256"] == row["image_sha256"]
        assert p["instruction"] == row["instruction"] and p["prompt"] == row["instruction"]
        for path, sha in zip(row["images"], row["image_sha256"], strict=True):
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
        v = p["rounded_action"]
        action = CODEBOOK.index(v) if p["tokens_in_action_range"] and v in CODEBOOK else None
        native.append(
            {
                "id": row["id"],
                "action_id": action,
                "raw": json.dumps(
                    {"tokens": p["action_token_ids"], "vector": p["raw_action"], "rounded": v}
                ),
                "target": row["action_id"],
            }
        )
    models["openfly_vla"] = native
    scores = {}
    for name, ps in models.items():
        for p in ps:
            p["direction_id"] = 1 if p["action_id"] in (8, 9) else p["action_id"]
            p["exact"] = p["action_id"] == p["target"]
            p["direction_correct"] = p["direction_id"] == p["target"]
            p["label"] = "INVALID" if p["action_id"] is None else LABELS[p["action_id"]]
        correct = sum(p["direction_correct"] for p in ps)
        scores[name] = {
            "n": 72,
            "direction_correct": correct,
            "exact_primitive": sum(p["exact"] for p in ps),
            "valid_codebook": sum(p["action_id"] is not None for p in ps),
            "false_stop": sum(p["action_id"] == 0 and p["target"] != 0 for p in ps),
            "macro_recall": sum(
                sum(p["direction_correct"] for p in ps if p["target"] == a) / 12 for a in range(6)
            )
            / 6,
            "predicted_actions": dict(collections.Counter(p["label"] for p in ps)),
        }
    gallery = {r["id"]: r for r in json.loads((VIEW / "joint_openfly_cases.json").read_text())}
    cases = [
        dict(
            id=r["id"],
            target=LABELS[r["action_id"]],
            instruction=r["instruction"],
            image_sha256=r["image_sha256"],
            previews=gallery[r["id"]]["previews"],
            outputs={name: ps[i] for name, ps in models.items()},
        )
        for i, r in enumerate(rows)
    ]
    result = {
        "model_label": "openfly_vla",
        "dataset_label": "openfly_vla data",
        "scores": scores,
        "cases": cases,
        "size": json.loads((REPORT / "dataset_size.json").read_text()),
        "protocol": "Same 72cases/route instructions/three causal images; model-specific formatting and preprocessing. Released vlnv1/raw instruction; NF4. Direction agreement credits forward6/9m; exact primitive does not. Unknown vectors never become STOP.",
        "training_overlap_warning": "These routes are held out from our adapters but belong to official TRAIN, so openfly_vla may have seen them. Not an equal-unseen test or an official benchmark.",
        "local_comparison": "Local velocity-JSON exact scores are not defined for the native OpenFly vector; no velocity conversion or openfly_vla flights claimed.",
    }
    (REPORT / "comparison.json").write_text(
        json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2)
    )
    (REPORT / "predictions.json").write_text(json.dumps(models, indent=2))
    (REPORT / "probe.json").write_text(json.dumps(probe, indent=2))
    (VIEW / "openfly_same_panel.json").write_text(json.dumps(result))
    (VIEW / "openfly_same_panel.html").write_text(PAGE, encoding="utf-8")
    print(json.dumps(scores))


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>openfly_vla model comparison</title><style>body{background:#0d1827;color:#e5edf7;font:16px system-ui;max-width:1200px;margin:24px auto;padding:0 18px}section{background:#17283b;padding:20px;border-radius:12px;margin:18px 0}p{line-height:1.5}a{color:#80c9ff}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #435268}select{max-width:100%;padding:10px;background:#263d56;color:white}img{width:31%;margin-right:1%}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warning{color:#ffd08a}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.card{background:#24364b;padding:15px;border-radius:8px}@media(max-width:650px){.grid{grid-template-columns:1fr}}</style><h1>openfly_vla vs our trained models</h1><section class="warning"><b>D146 investigation: this is not a validated model ranking.</b><p>The vlnv1 decoder forces up/down outputs to zero, making 24/72 labels unreachable for openfly_vla. Motion/image checks passed, but the released prompt, history encoding and normalization interfaces conflict. Historical scores are preserved below.</p><a href="openfly_forensics.html">Read the investigation and controlled tests</a></section><p><b>openfly_vla</b> = released 7B model, run in 4-bit. <b>openfly_vla data</b> = the OpenFly dataset used for this comparison.</p><section><h2>How much data?</h2><div id="size"></div><p>Paper: about 100K trajectories across 18 scenes. The downloaded annotation manifests cover 103,226 routes; the training manifest contains 11 environment IDs. These describe different scopes, not an assertion that all released assets were downloaded.</p><p><a href="https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly">Official dataset repository</a> Â· <a href="https://arxiv.org/abs/2502.18041">Paper</a></p></section><section><h2>Same 72 cases from openfly_vla data</h2><p id="warning" class="warning"></p><div class="scroll"><table id="scores"></table></div><p>12 examples per action. Always-forward:12/72 (16.7%). Direction agreement allows forward 6m/9m predictions; exact primitive requires the same next atomic action. All our models emit six atomic IDs, so their two counts coincide.</p><p id="protocol"></p><p id="local"></p></section><section><h2>Same observation, four actual outputs</h2><select id="case"></select><div id="images"></div><p id="instruction"></p><p id="target"></p><div id="outputs" class="grid"></div><details><summary>Source identity and image hashes</summary><pre id="provenance"></pre></details></section><p><a href="joint_openfly.html">Training losses and our actual simulation flights</a> Â· <a href="openfly_clips.html">Recorded source clips</a></p><script>let data;const $=id=>document.getElementById(id),esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function show(){let c=data.cases[+$('case').value||0];$('images').innerHTML=c.previews.map(p=>`<img src="${p}" alt="Causal source observation">`).join('');$('instruction').textContent=c.instruction;$('target').textContent='Recorded next action: '+c.target;$('provenance').textContent=JSON.stringify({id:c.id,image_sha256:c.image_sha256},null,2);$('outputs').innerHTML=Object.entries(c.outputs).map(([n,p])=>`<div class="card"><b>${n}</b><p>${esc(p.label)}</p><p>Direction: ${p.direction_correct?'correct':'wrong'} Â· exact primitive: ${p.exact?'correct':'wrong'}</p><details><summary>Actual raw output</summary><pre>${esc(p.raw)}</pre></details></div>`).join('')}fetch('openfly_same_panel.json').then(r=>r.json()).then(d=>{data=d;$('size').innerHTML=`<p><b>${d.size.total_routes.toLocaleString()} routes</b> and <b>${d.size.total_annotated_decisions.toLocaleString()} annotated decisions</b>:100,226 training routes + 1,800 seen-evaluation + 1,200 unseen-evaluation.</p><p>Repository file size: <b>${d.size.repository_size_display}</b>. This may include alternative representations; it is not the required size of one training copy. Annotated decisions may aggregate several raw steps.</p><p>Our pilot prepared 110 routes (88 train/22 validation): 2,929 OpenFly training decisions and 815 validation decisions. Each model actually saw 592 unique OpenFly examples, repeated into 1,600 exposures; plus 790 unique local examples. All prepared sources combined: 5,200 examples (4,085 train/1,115 validation).</p>`;$('warning').textContent=d.training_overlap_warning;$('protocol').textContent=d.protocol;$('local').textContent=d.local_comparison;$('scores').innerHTML='<tr><th>Model</th><th>Direction agreement</th><th>Exact primitive</th><th>Valid action</th><th>False STOP /60</th></tr>'+Object.entries(d.scores).map(([n,s])=>`<tr><td>${n}</td><td>${s.direction_correct}/72 (${(100*s.direction_correct/72).toFixed(1)}%)</td><td>${s.exact_primitive}/72</td><td>${s.valid_codebook}/72</td><td>${s.false_stop}/60</td></tr>`).join('');$('case').innerHTML=d.cases.map((c,i)=>`<option value="${i}">${i+1} Â· ${esc(c.target)} Â· ${esc(c.id.slice(-80))}</option>`).join('');$('case').onchange=show;show()});</script></html>"""

if __name__ == "__main__":
    build()
