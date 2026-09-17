# ruff: noqa: E501
"""Portable exact-input/prediction review for the frozen mixed local validation set."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path

from PIL import Image


def uri(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def build(data, reports, out):
    manifest = json.loads((data / "manifest.json").read_text())
    assert (
        hashlib.sha256((data / "index.jsonl").read_bytes()).hexdigest() == manifest["index_sha256"]
    )
    by_id = {
        r["decision_id"]: r
        for r in [json.loads(line) for line in (data / "index.jsonl").read_text().splitlines()]
    }
    rows = []
    reference = json.loads((reports / "existing_control_report.json").read_text())
    review_ids = manifest["generation_eval_ids"] + reference["extra_eval_ids"]
    for identity in review_ids:
        r = by_id[identity]
        p = Path(r["data_root"]) / r["images"]["mosaic"]
        assert hashlib.sha256(p.read_bytes()).hexdigest() == r["image_sha256"]["mosaic"]
        rows.append(
            dict(
                id=identity,
                instruction=r["instruction"],
                prompt=r["prompt"],
                blank_prompt=r["prompt"].replace(
                    r["instruction"], "Perform the requested task.", 1
                ),
                target=r["target"],
                task=r["task_group"],
                image=uri(p),
                state=r["state"],
            )
        )
    models = {}
    for name in ("existing_control", "expanded"):
        path = reports / f"{name}_report.json"
        if not path.exists():
            continue
        r = json.loads(path.read_text())
        assert r["status"] == "complete"
        models[name] = {
            "before": {v["decision_id"]: v for v in r["before"]},
            "after": {v["decision_id"]: v for v in r["after"] + r["extra_after"]},
        }
        for kind in ("blank_image", "blank_instruction"):
            models[name][kind] = {
                v["decision_id"]: v for v in r["interventions"] if v["intervention"] == kind
            }
    for name in models:
        execution_path = reports / f"{name}_visual_execution.json"
        models[name]["executions"] = {}
        if execution_path.exists():
            execution = json.loads(execution_path.read_text())
            for result in execution["segments"]:
                image_path = Path(execution["output_root"]) / result["id"] / "after.png"
                if image_path.exists():
                    assert (
                        hashlib.sha256(image_path.read_bytes()).hexdigest()
                        == result["after_image_sha256"]
                    )
                    models[name]["executions"][result["id"]] = {
                        "image": uri(image_path),
                        "reduced": result["visible_error_reduced"],
                        "translation_m": result["translation_m"],
                    }
    assert models
    b = io.BytesIO()
    Image.new("RGB", (224, 224), (127, 127, 127)).save(b, format="PNG")
    payload = dict(
        rows=rows,
        models=models,
        full_plot=uri(reports / "training_loss_curves.png")
        if (reports / "training_loss_curves.png").exists()
        else None,
        task_plot=uri(reports / "task_loss_curves.png")
        if (reports / "task_loss_curves.png").exists()
        else None,
        loss_plot=uri(reports / "validation_loss_curves.png")
        if (reports / "validation_loss_curves.png").exists()
        else None,
        blank="data:image/png;base64," + base64.b64encode(b.getvalue()).decode(),
    )
    html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Balanced original versus expanded data</title><style>body{font:16px system-ui;background:#101a2a;color:#e0e8f3;margin:24px}main{max-width:1100px;margin:auto}select{padding:9px;max-width:100%;margin:5px 0}#sample{width:100%}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{width:100%;max-width:448px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#1c2b40;padding:14px}p{line-height:1.5}a{color:#86d2fc}.bad{color:#ffa693}.good{color:#8de6b4}@media(max-width:700px){.grid{grid-template-columns:1fr}body{margin:12px}}</style><main><h1>Balanced original versus expanded data</h1><p>Smol256 trained on 252 original or 1,156 expanded examples. Both runs use 400 updates / 1,600 exposures, one visual + motion + HOLD + STOP per effective batch. Original 84 validation rows remain unchanged; 216 new validation rows are measured separately. Generation probes were fixed before training. Visual pairs test whether changing the image or instruction changes the action. These are saved predictions, not live flights.</p><details id="lossSection"><summary>Training and validation loss curves</summary><p>Both conditions use identical loss definitions in evaluation mode at steps 0, 200 and 400. Left: original validation; right: new-scene validation. Top: weighted action loss; bottom: ordinary answer-token loss. Lower loss does not establish correct flight behavior.</p><img id="lossPlot" alt="Measured training and validation loss curves" style="max-width:100%"></details><details id="fullSection"><summary>Loss on each condition's own training set (different populations)</summary><img id="fullPlot" alt="Full measured checkpoint loss history" style="max-width:100%"></details><details id="taskSection"><summary>Loss by visual / motion / HOLD / STOP task</summary><img id="taskPlot" alt="Measured task-specific training and validation losses" style="max-width:100%"></details><label>Model <select id="model"></select></label> <label>Condition <select id="phase"><option value="after">After 400 mixed-batch updates</option><option value="before">Zero-shot before training</option><option value="blank_image">Trained: image blanked</option><option value="blank_instruction">Trained: task instruction removed</option></select></label><select id="sample"></select><h2 id="instruction"></h2><p id="status"></p><div class="grid"><div><img id="image" alt="Exact input mosaic"><p>Front RGB above downward RGB. Gray is the actual blank-image intervention.</p><pre id="state"></pre><h3>Saved action: result after 0.2 simulated seconds</h3><img id="afterImage" alt="Result of executing the saved model action"><p id="afterStatus"></p></div><div><h3>Teacher target</h3><pre id="target"></pre><h3>Actual model output</h3><pre id="raw"></pre><h3>Decoded physical setpoint</h3><pre id="physical"></pre></div></div><details><summary>Exact model text prompt</summary><pre id="prompt"></pre></details><p>Velocities use the source-heading-level forward/right/down frame. Positive yaw is clockwise viewed from above. STOP ends the mission; it is not physical landing. Bins32 mean zero. Output is held for0.2 simulated seconds; measured inference is slower.</p><p><a href="data_expansion.html">Dataset sources</a> · <a href="balanced_control_flights.html">Original-data model flights</a> · <a href="balanced_expanded_flights.html">Expanded-data model flights</a></p></main><script>const DATA=__DATA__;document.getElementById('lossSection').hidden=!DATA.loss_plot;if(DATA.loss_plot)document.getElementById('lossPlot').src=DATA.loss_plot;document.getElementById('fullSection').hidden=!DATA.full_plot;if(DATA.full_plot)document.getElementById('fullPlot').src=DATA.full_plot;document.getElementById('taskSection').hidden=!DATA.task_plot;if(DATA.task_plot)document.getElementById('taskPlot').src=DATA.task_plot;const model=document.getElementById('model'),phase=document.getElementById('phase'),sample=document.getElementById('sample');for(const name of Object.keys(DATA.models)){const o=document.createElement('option');o.value=name;o.textContent=name==='existing_control'?'Original data / balanced':'Expanded data / balanced';model.append(o)}DATA.rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${r.task} / ${r.id}`;sample.append(o)});function text(id,v){document.getElementById(id).textContent=v}function draw(){const r=DATA.rows[Number(sample.value)],p=DATA.models[model.value][phase.value][r.id];text('instruction',phase.value==='blank_instruction'?'Perform the requested task.':r.instruction);document.getElementById('image').src=phase.value==='blank_image'?DATA.blank:r.image;text('state',JSON.stringify(r.state,null,2));text('target',JSON.stringify(r.target,null,2));text('raw',p?p.raw:'No saved prediction for this probe and condition. Blank-input interventions cover the original visual probes.');text('status',p?`${p.valid?'Valid JSON':'INVALID OUTPUT'} · ${p.exact?'exact target':'does not match target'} · generation ${p.latency_s.toFixed(3)}s`:'Not evaluated');document.getElementById('status').className=p&&p.exact?'good':'bad';let physical='Invalid/unavailable: no decoded model command';if(p&&p.valid){const a=p.parsed;physical=JSON.stringify({forward_mps:(a.forward_bin-32)*10/64,right_mps:(a.right_bin-32)*10/64,down_mps:(a.down_bin-32)*10/64,yaw_clockwise_rps:(a.yaw_cw_bin-32)*3/64,mission_stop:a.stop},null,2)}const execution=phase.value==='after'?DATA.models[model.value].executions[r.id]:null;document.getElementById('afterImage').style.display=execution?'block':'none';if(execution)document.getElementById('afterImage').src=execution.image;text('afterStatus',execution?`Target angular error ${execution.reduced?'decreased':'did not decrease'}; translation ${execution.translation_m.toFixed(3)}m.`:'No execution image for this probe/condition.');text('physical',physical);text('prompt',phase.value==='blank_instruction'?r.blank_prompt:r.prompt)}model.onchange=phase.onchange=sample.onchange=draw;draw();</script></html>"""
    out.write_text(
        html.replace("__DATA__", json.dumps(payload).replace("<", "\\u003c")), encoding="utf-8"
    )
    print(list(models))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--reports", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    build(a.data, a.reports, a.out)
