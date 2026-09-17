"""D141 local training progress and official OpenFly offline transfer review."""

# ruff: noqa: E501, SIM105
import base64
import hashlib
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from summarize_balanced_comparison import loss_points, summarize

from uavlab.training.openfly_eval import frd_class, native_class, score

OUT = Path("reports/vla_expanded_models_20260917")
VIEW = Path("reports/vla_dataset_review_20260916")
BASE = Path("D:/drone_vla_pilot/runs")
FOLDERS = {
    "smol256": "smol256_balanced_expanded_20260917_a",
    "smol500": "smol500_expanded_20260917_a",
    "qwen": "qwen_expanded_20260917_a",
}
local_rows = [
    json.loads(x)
    for x in Path("D:/drone_vla_pilot/data/local_expanded_20260917_v4/index.jsonl")
    .read_text()
    .splitlines()
]
eval_path = Path("D:/drone_vla_pilot/data/openfly_eval_20260917/eval.jsonl")
rows = [json.loads(x) for x in eval_path.read_text().splitlines()]
data_hash = hashlib.sha256(eval_path.read_bytes()).hexdigest()
local = {}
native = {}
predictions = {}
training_reports = {}
for model, folder in FOLDERS.items():
    file = BASE / folder / "report.json"
    if file.exists():
        try:
            r = json.loads(file.read_text())
        except json.JSONDecodeError:
            continue
        training_reports[model] = r
        local[model] = dict(status=r["status"], updates=r["updates"])
        log = BASE / folder / "losses.jsonl"
        if log.exists():
            lines = log.read_text().splitlines()
            try:
                local[model]["updates"] = json.loads(lines[-1])["step"]
            except (json.JSONDecodeError, IndexError):
                pass
        if r["status"] == "complete":
            local[model]["metrics"] = summarize(r, local_rows)
            (OUT / f"{model}_training_report.json").write_text(json.dumps(r, indent=2))
    else:
        local[model] = dict(status="preparing or queued", updates=0)
    path = BASE / f"{model}_openfly_transfer_20260917" / "report.json"
    if path.exists():
        r = json.loads(path.read_text())
        assert r["data_sha256"] == data_hash
        by = {x["id"]: x for x in r["outputs"]}
        assert set(by) == {x["id"] for x in rows}
        predictions[model] = [
            dict(by[row["id"]], coarse_class=frd_class(by[row["id"]]["parsed"])) for row in rows
        ]
        native[model] = score(rows, [x["coarse_class"] for x in predictions[model]])
        (OUT / f"{model}_transfer_report.json").write_text(json.dumps(r, indent=2))
path = BASE / "openfly_official_eval_20260917" / "probe.json"
if path.exists():
    r = json.loads(path.read_text())
    assert r["evaluation_data_sha256"] == data_hash
    by = {x["decision_id"]: x for x in r["outputs"]}
    assert set(by) == {x["id"] for x in rows}
    predictions["openfly"] = [
        dict(
            by[row["id"]],
            coarse_class=native_class(by[row["id"]]["rounded_action"])
            if by[row["id"]]["tokens_in_action_range"]
            else "invalid",
        )
        for row in rows
    ]
    native["openfly"] = score(rows, [x["coarse_class"] for x in predictions["openfly"]])
    (OUT / "openfly_transfer_report.json").write_text(json.dumps(r, indent=2))
summary = dict(
    local=local,
    official_transfer=native,
    evaluation_data_sha256=data_hash,
    limits="51-frame offline development diagnostic, not official full benchmark or flight success. Different model input/history interfaces; no external fine-tuning.",
)
(OUT / "summary.json").write_text(json.dumps(summary, indent=2))
fig, axes = plt.subplots(3, 2, figsize=(11, 10), layout="constrained")
for i, model in enumerate(FOLDERS):
    r = training_reports.get(model)
    for j, cohort in enumerate(("original", "new_scenes")):
        ax = axes[i, j]
        ax.set_title(f"{model}: {cohort}")
        ax.set_xlabel("Optimizer updates")
        ax.set_ylabel("Weighted action loss")
        ax.grid(alpha=0.2)
        if r and "initial_losses" in r:
            r = dict(r, comparable_losses=r.get("comparable_losses", []))
            for split in ("train", "val"):
                points = loss_points(r, cohort, split)
                ax.plot(
                    [p[0] for p in points],
                    [p[1]["weighted_action_loss"] for p in points],
                    marker="o",
                    label=split,
                )
            ax.legend()
        else:
            ax.text(0.5, 0.5, "Pending", ha="center", transform=ax.transAxes)
fig.suptitle("Expanded data: eval-mode TRAIN and VAL losses; compare trends within each model")
fig.savefig(OUT / "loss_curves.png", dpi=140)
plt.close(fig)
plot = base64.b64encode((OUT / "loss_curves.png").read_bytes()).decode()
review_rows = []
for row in rows:
    image = Image.open(row["images"][-1]).convert("RGB")
    image.thumbnail((640, 480))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    review_rows.append(
        dict(row, preview="data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    )
blob = json.dumps(dict(summary=summary, rows=review_rows, predictions=predictions)).replace(
    "<", "\\u003c"
)
page = """<!doctype html><meta charset='utf-8'><title>Expanded models and OpenFly evaluation</title>
<style>body{font:16px system-ui;background:#0d1725;color:#dfeaf5;max-width:1200px;margin:auto;padding:24px}a{color:#64d5e3}section{background:#172537;border:1px solid #41536b;padding:18px;margin:18px 0;border-radius:10px}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #41536b}img{max-width:100%}select{max-width:100%;padding:10px;background:#20344b;color:white}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:450px;overflow:auto}small{color:#a4b8cf}.scroll{overflow:auto}</style>
<h1>Expanded-data models and official OpenFly evaluation</h1>
<p>Smol256 reference; fresh Smol500 and Qwen3-VL4B runs,400updates each. OpenFly stays4-bit.</p>
<section><h2>Local training status</h2><div class='scroll'><table id='local'></table></div><p>Behavioral scores use the same frozen local probes. Cross-model token losses are not a model ranking.</p><details><summary>Training and validation loss curves</summary><img id='plot' alt='Within-model training and validation loss'></details></section>
<section><h2>Official OpenFly data: offline action comparison</h2><p>51decisions,14trajectories,seen/unseen. Evaluating coarse action category only;not flight success or exact command magnitude. Always-forward reference:26/51.</p><p>OpenFly:front images with preceding history. Our adapters:current front image;missing downward camera and odometry explicitly declared. This is a transfer limitation. No evaluation rows used for training.</p><div class='scroll'><table id='scores'></table></div><p>Tasks: multi-stage landmark route following, such as approach a building, turn toward a second landmark, continue and stop. This is expert-trajectory next-action scoring, not autonomous flights.</p><p>Integration remains unresolved: model-card normalization vln_norm differs from released evaluator vlnv1; our causal preceding history differs from the released training history sampler. Do not interpret this as the published OpenFly benchmark score. <a href="openfly_training.html">New official-TRAIN pilot and source trajectories</a>.</p><p>Accuracy and macro recall shown separately;mixed commands and invalid outputs are failures for this strict category metric.</p></section>
<section><h2>Inspect source and prediction</h2><select id='case'></select><p id='instruction'></p><img id='image' alt='Preview of exact source front image'><p id='target'></p><small>Preview resized for display;original imageSHA256 and source path below. Target labels never enter model prompts.</small><p><select id='model'></select></p><pre id='output'></pre><details><summary>Source provenance</summary><pre id='source'></pre></details></section>
<section><h2>Local simulation flights</h2><a href='balanced_expanded_flights.html#run=smol256_mixed_frd_trained_s1400'>Smol256 expanded</a> | <a href='smol500_expanded_flights.html#run=smol500_mixed_frd_trained_s1400'>Smol500 expanded</a> | <a href='qwen_expanded_flights.html#run=qwen_mixed_frd_trained_s1400'>Qwen expanded</a><p>New flight pages appear after their evaluation finishes. Local simulations pause during inference.</p></section>
<script>const DATA=__DATA__;document.querySelector('#plot').src='data:image/png;base64,__PLOT__';
const el=id=>document.getElementById(id);function table(id,headers,rows){const t=el(id);for(const row of [headers,...rows]){const tr=document.createElement('tr');for(const value of row){const td=document.createElement('td');td.textContent=value;tr.append(td)}t.append(tr)}}
table('local',['Model','Status','Updates','Visual original/new','STOP exact','False STOP'],Object.entries(DATA.summary.local).map(([k,v])=>{const m=v.metrics;return[k,v.status,v.updates,m?`${m.original.visual.correct_yaw_without_translation_or_stop}/16; ${m.new.visual.correct_yaw_without_translation_or_stop}/64`:'pending',m?`${m.boundaries.stop.exact}/6`:'pending',m?Object.entries(m.boundaries).filter(([k])=>k!=='stop').reduce((a,[k,v])=>a+v.predicted_stop,0)+'/128':'pending']}));
table('scores',['Model','All','Seen','Unseen','Macro recall','Invalid','Mixed actions','False STOP'],Object.entries(DATA.summary.official_transfer).map(([k,v])=>[k,`${v.all.correct}/${v.all.n}`,`${v.seen.correct}/${v.seen.n}`,`${v.unseen.correct}/${v.unseen.n}`,(100*v.all.macro_recall).toFixed(1)+'%',`${v.all.invalid}/${v.all.n}`,`${v.all.mixed}/${v.all.n}`,`${v.all.false_stop}/${v.all.nonterminal}`]));
DATA.rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${r.split} | ${r.environment} | frame ${r.index} | ${r.target_class}`;el('case').append(o)});
for(const m of ['openfly','smol256','smol500','qwen']){const o=document.createElement('option');o.value=m;o.textContent=m+(DATA.predictions[m]?'':' (pending)');el('model').append(o)}
function show(){const i=Number(el('case').value),r=DATA.rows[i];el('image').src=r.preview;el('instruction').textContent=r.instruction;el('target').textContent='Recorded target: '+r.target_class+'; native annotation ID '+r.target_id;el('output').textContent=JSON.stringify(DATA.predictions[el('model').value]?.[i]??{status:'pending'},null,2);const {preview,...source}=r;el('source').textContent=JSON.stringify(source,null,2)}el('case').onchange=show;el('model').onchange=show;show();</script>"""
page = page.replace("__DATA__", blob).replace("__PLOT__", plot)
(VIEW / "expanded_models.html").write_text(page, encoding="utf-8")
print(json.dumps({k: {"status": v["status"], "updates": v["updates"]} for k, v in local.items()}))
