# ruff: noqa: E501
"""Audit and display D147 repaired decoding, alignment and matched controls."""

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_repair_20260918"
VIEW = ROOT / "reports/vla_dataset_review_20260916"
LABELS = [
    "STOP",
    "forward 3 m",
    "left turn",
    "right turn",
    "up 3 m",
    "down 3 m",
    "left",
    "right",
    "forward 6 m",
    "forward 9 m",
]


def direction(a):
    return 1 if a in (8, 9) else a


def score(rows, pred):
    targets = [direction(r["action_id"]) for r in rows]
    ps = [direction(p) for p in pred]
    matrix = [[0] * 7 for _ in range(6)]
    for t, p in zip(targets, ps, strict=True):
        matrix[t][p if p in range(6) else 6] += 1
    return dict(
        n=len(rows),
        direction_correct=sum(p == t for p, t in zip(ps, targets, strict=True)),
        valid=sum(p is not None for p in pred),
        per_action=[
            dict(action=LABELS[a], correct=matrix[a][a], n=sum(matrix[a])) for a in range(6)
        ],
        confusion=matrix,
        confusion_columns=["STOP", "forward", "left turn", "right turn", "up", "down", "invalid"],
    )


def main():
    original = list(map(json.loads, (OUT / "rerun_inputs.jsonl").read_text().splitlines()))
    aligned = list(map(json.loads, (OUT / "aligned_panel.jsonl").read_text().splitlines()))
    probe = json.loads((OUT / "repaired_probe.json").read_text())
    outputs = probe["outputs"]
    assert (
        probe["evaluation_data_sha256"]
        == hashlib.sha256((OUT / "rerun_inputs.jsonl").read_bytes()).hexdigest()
    )
    assert len(outputs) == 120 and all(o["generated_token_count"] == 8 for o in outputs)
    fresh = json.loads(
        Path("D:/drone_vla_pilot/runs/openfly_aligned_20260918/probe.json").read_text()
    )
    assert fresh["coverage"]["roundtrip_actions"] == [0, 1, 2, 3, 4, 5, 8, 9]
    assert (
        fresh["evaluation_data_sha256"]
        == hashlib.sha256((OUT / "aligned_panel.jsonl").read_bytes()).hexdigest()
    )
    (OUT / "aligned_openfly_probe.json").write_text(json.dumps(fresh, indent=2))
    old_by = {o["decision_id"]: o for o in outputs}
    new_pred = {o["decision_id"]: o for o in fresh["outputs"]}
    new_models = {
        "openfly_vla": [new_pred[r["id"]]["strict_decoded"]["action_id"] for r in aligned]
    }
    cases = [
        dict(
            row=r,
            outputs={
                "openfly_vla": dict(
                    action_id=new_pred[r["id"]]["strict_decoded"]["action_id"],
                    raw=json.dumps(new_pred[r["id"]]["strict_decoded"]),
                )
            },
        )
        for r in aligned
    ]
    controls = {}
    gray = original[96:]
    for model in ["openfly_vla", "smol256", "smol500", "qwen"]:
        if model == "openfly_vla":

            def get(identity):
                return old_by[identity]["strict_decoded"]["action_id"]

            unchanged = None
        else:
            data = json.loads((OUT / (model + "_controls.json")).read_text())
            by = {r["id"]: r for r in data["outputs"]}

            def get(identity, by=by):
                return by[identity]["action_id"]

            legacy = json.loads(
                (
                    ROOT / f"reports/vla_joint_openfly_20260917/{model}_training_report.json"
                ).read_text()
            )
            legacy_by = {r["id"]: r for r in legacy["after"]}
            unchanged = sum(r["raw"] == legacy_by[r["id"]]["raw"] for r in data["outputs"][:24])
            assert unchanged == 24, (
                "Original predictions must reproduce before new controls are interpreted"
            )
            new = json.loads((OUT / (model + "_aligned.json")).read_text())
            nb = {r["id"]: r for r in new["outputs"]}
            new_models[model] = [nb[r["id"]]["action_id"] for r in aligned]
            for case in cases:
                case["outputs"][model] = nb[case["row"]["id"]]
        originals = [dict(r, id=r["id"].removeprefix("gray:")) for r in gray]
        controls[model] = dict(
            original=score(originals, [get(r["id"]) for r in originals]),
            gray=score(gray, [get(r["id"]) for r in gray]),
            changed_actions=sum(get(r["id"]) != get(r["id"].removeprefix("gray:")) for r in gray),
            macro_annotation=score(original[72:96:2], [get(r["id"]) for r in original[72:96:2]]),
            macro_start=score(original[73:96:2], [get(r["id"]) for r in original[73:96:2]]),
            reproduced_originals=unchanged,
        )
    scores = {m: score(aligned, p) for m, p in new_models.items()}
    exact = sum(
        p == r["action_id"] for p, r in zip(new_models["openfly_vla"], aligned, strict=True)
    )
    audit = json.loads((OUT / "full_data_audit.json").read_text())
    prepared = json.loads((ROOT / "reports/vla_joint_openfly_20260917/data_audit.json").read_text())
    assert {(x["trajectory"], x["frame"]) for x in audit["issues"]} == {
        (x["trajectory"], x["frame"]) for x in prepared["excluded"]
    }
    dataset = Path("D:/drone_vla_pilot/data/joint_openfly_local_20260917_v1/index.jsonl")
    assert hashlib.sha256(dataset.read_bytes()).hexdigest() == prepared["index_sha256"]
    summary = dict(
        status="complete",
        same72_repaired=score(
            original[:72], [o["strict_decoded"]["action_id"] for o in outputs[:72]]
        ),
        aligned_scores=scores,
        openfly_aligned_exact_macro=exact,
        controls=controls,
        counts=audit["counts"],
        macro_backward_only=audit["macro_backward_only"],
        preserved_data_sha256=prepared["index_sha256"],
        calibration="Explicit vlnv11 adapter passes action coverage; original checkpoint calibration mapping remains unverified",
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    assets = VIEW / "repair_assets"
    assets.mkdir(exist_ok=True)
    for case in cases:
        r = case["row"]
        previews = []
        for path, sha in zip(r["images"], r["image_sha256"], strict=True):
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
            dest = assets / (sha[:20] + ".jpg")
            if not dest.exists():
                with Image.open(path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((480, 320))
                    im.save(dest, quality=85)
            previews.append("repair_assets/" + dest.name)
        case["previews"] = previews
    shutil.copyfile(OUT / "alignment_example.png", assets / "alignment_example.png")
    (VIEW / "openfly_repair.json").write_text(
        json.dumps(dict(summary=summary, cases=cases, labels=LABELS))
    )
    (VIEW / "openfly_repair.html").write_text(PAGE, encoding="utf-8")
    print(json.dumps(scores))
    print(
        json.dumps(
            {
                m: {k: v["direction_correct"] for k, v in c.items() if isinstance(v, dict)}
                for m, c in controls.items()
            }
        )
    )


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>OpenFly decoder and data repair</title><style>body{background:#102033;color:#edf4ff;font:17px system-ui;max-width:1150px;margin:25px auto;padding:0 18px;line-height:1.5}section{background:#1b3048;padding:20px;border-radius:10px;margin:18px 0}a{color:#84cfff}.warning{color:#ffce8b}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:left;border-bottom:1px solid #5a6c80}select{max-width:100%;padding:10px;background:#213b55;color:white}pre{white-space:pre-wrap;overflow-wrap:anywhere}.images{display:flex;gap:8px}.images img{width:32%}.wide{width:100%}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.card{background:#263e58;padding:12px;border-radius:8px}@media(max-width:600px){.grid{grid-template-columns:1fr}.images{flex-wrap:wrap}.images img{width:100%}}</style><h1>OpenFly: decoder fixed, alignment corrected</h1><section><h2>What was wrong?</h2><p><b>Decoder:</b> the old setting erased up/down. The new explicit profile can represent every evaluated action, with round-trip checks. Up/down predictions now reach the evaluator.</p><p><b>Data alignment:</b> compressed forward commands referenced the last raw frame inside a movement block. We reconstructed and verified their start frames without changing the old dataset.</p><img class="wide" src="repair_assets/alignment_example.png" alt="A 9 metre action begins at frame zero; the old annotation selected frame two, with only three metres remaining."><p><b>110 routes audited:</b> 3,634 movement labels pass; eight mismatches remain excluded. The separate corrected macro manifest contains 1,639 examples, keeping 88 train/22 validation routes.</p></section><section><h2>Fresh comparison on corrected examples</h2><p>Same72 observations and route instructions, 12 examples per direction, unchanged checkpoints. Main metric: next-direction agreement. This is not flight success. Our adapters only output3m forward, so exact macro distance is reported separately for OpenFly.</p><div class="scroll"><table id="scores"></table></div><p id="exact"></p><p class="warning" id="calibration"></p><p>Always-forward reference:12/72. These official TRAIN routes are held out from our adapters; the released model may have seen them. No statistically reliable winner or published-benchmark reproduction is claimed.</p></section><section><h2>Additional data and precision checks</h2><p>9,728 training routes use initial-climb (-1) and post-STOP-descent (-2) tags. Our pilot excluded those routes. The new schema parser preserves those phases and uses the recorded navigation STOP as the navigation goal.</p><p>8,160 of those routes place STOP more than20m from the final recorded position. Treating that later position as the navigation goal would conflict with the STOP label.</p><p>A six-case unquantized BF16 reference produced the same decoded actions as NF4 on all six. Quantization alone does not explain those failures; full-panel equivalence remains untested.</p></section><section><h2>Controlled checks</h2><div class="scroll"><table id="controls"></table></div><p>Gray-image tests remove visual information on the same24 balanced cases. The12 macro pairs were specifically selected for a demonstrated alignment mismatch, so they diagnose that issue rather than estimate overall performance.</p></section><section><h2>Inspect the same input and four outputs</h2><select id="case"></select><div class="images" id="images"></div><p id="instruction"></p><p id="target"></p><div class="grid" id="outputs"></div><details><summary>Frame identity and source hashes</summary><pre id="provenance"></pre></details></section><p><a href="openfly_forensics.html">Previous investigation</a> · <a href="openfly_same_panel.html">Preserved original comparison</a></p><script>const $=id=>document.getElementById(id);let data;const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function show(){let c=data.cases[+$('case').value||0];$('images').innerHTML=c.previews.map(x=>`<img src="${x}" alt="Causal source frame">`).join('');$('instruction').textContent=c.row.instruction;$('target').textContent='Recorded command: '+data.labels[c.row.action_id]+' · original annotation frame '+c.row.annotation_frame+' → verified action start '+c.row.frame_index;$('provenance').textContent=JSON.stringify(c.row,null,2);$('outputs').innerHTML=Object.entries(c.outputs).map(([m,p])=>`<div class="card"><b>${m}</b><p>${p.action_id===null?'INVALID':data.labels[p.action_id]}</p><details><summary>Raw output</summary><pre>${esc(p.raw)}</pre></details></div>`).join('')}fetch('openfly_repair.json').then(r=>r.json()).then(d=>{data=d;$('scores').innerHTML='<tr><th>Model</th><th>Direction /72</th><th>Valid /72</th><th>Up /12</th><th>Down /12</th></tr>'+Object.entries(d.summary.aligned_scores).map(([m,s])=>`<tr><td>${m}</td><td>${s.direction_correct}/72</td><td>${s.valid}/72</td><td>${s.per_action[4].correct}/12</td><td>${s.per_action[5].correct}/12</td></tr>`).join('');$('exact').textContent='openfly_vla exact macro agreement: '+d.summary.openfly_aligned_exact_macro+'/72.';$('calibration').textContent=d.summary.calibration;$('controls').innerHTML='<tr><th>Model</th><th>Real images /24</th><th>Gray images /24</th><th>Original macro frame /12</th><th>Verified start /12</th></tr>'+Object.entries(d.summary.controls).map(([m,c])=>`<tr><td>${m}</td><td>${c.original.direction_correct}</td><td>${c.gray.direction_correct}</td><td>${c.macro_annotation.direction_correct}</td><td>${c.macro_start.direction_correct}</td></tr>`).join('');$('case').innerHTML=d.cases.map((c,i)=>`<option value="${i}">${i+1}: ${d.labels[c.row.action_id]} · ${esc(c.row.trajectory.split('/')[0])}</option>`).join('');$('case').onchange=show;show()});</script></html>"""


if __name__ == "__main__":
    main()
