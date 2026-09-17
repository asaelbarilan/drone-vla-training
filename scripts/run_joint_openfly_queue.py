# ruff: noqa: E501
"""D144 sequential GPU queue with live review and audited local flight playback."""

import base64
import io
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("D:/drone_vla_pilot")
PYTHON = BASE / "venv_qwen/Scripts/python.exe"
RUNS = BASE / "runs"
REPORT = ROOT / "reports/vla_joint_openfly_20260917"
VIEW = ROOT / "reports/vla_dataset_review_20260916"
MODELS = ("smol256", "smol500", "qwen")
NAMES = ("STOP", "forward 3m", "left turn 30°", "right turn 30°", "up 3m", "down 3m")


def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: finite_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [finite_json(v) for v in value]
    return value


def write(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(finite_json(value), allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def folder(model):
    return RUNS / f"{model}_joint_20260917_a"


def metrics(predictions):
    result = {}
    for source in ("local", "openfly"):
        rows = [r for r in predictions if r["source"] == source]
        if not rows:
            continue
        group = {}
        for key in sorted({r["group"] for r in rows}):
            selected = [r for r in rows if r["group"] == key]
            group[key] = sum(r["exact"] for r in selected) / len(selected)
        false_stop = sum(
            (r["parsed"] == 0 and r["target"] != 0)
            if source == "openfly"
            else bool(r["parsed"] and r["parsed"]["stop"] and not r["target"]["stop"])
            for r in rows
        )
        result[source] = dict(
            n=len(rows),
            exact=sum(r["exact"] for r in rows),
            valid=sum(r["valid"] for r in rows),
            false_stop=false_stop,
            group_accuracy=group,
        )
        if source == "openfly":
            result[source].update(
                macro_recall=sum(group.values()) / len(group),
                always_forward_exact=sum(r["target"] == 1 for r in rows),
            )
    return result


def snapshot(state):
    models = {}
    for name in MODELS:
        report = read(folder(name) / "report.json")
        if report:
            models[name] = {
                k: report[k]
                for k in (
                    "status",
                    "updates",
                    "elapsed_seconds",
                    "losses",
                    "comparable_losses",
                    "before",
                    "after",
                    "error",
                    "reload_matches",
                )
                if k in report
            }
            models[name]["metrics"] = {
                phase: metrics(report.get(phase, [])) for phase in ("before", "after")
            }
            write(REPORT / f"{name}_training_report.json", report)
        else:
            models[name] = dict(status="queued", updates=0)
        flight = read(RUNS / f"{name}_joint_flights_20260917_a/summary.json")
        if flight:
            models[name]["flights"] = flight
        models[name]["flight_ready"] = (VIEW / f"{name}_joint_flights.html").exists()
    write(VIEW / "joint_openfly_status.json", dict(state=state, updated=time.time(), models=models))
    write(REPORT / "queue_status.json", state)


def gallery():
    data = BASE / "data/joint_openfly_local_20260917_v1"
    manifest = read(data / "manifest.json")
    by = {r["id"]: r for r in map(json.loads, (data / "index.jsonl").read_text().splitlines())}
    cases = []
    for identity in manifest["evaluation_ids"]:
        row = by[identity]
        paths = (
            row["images"]
            if row["source"] == "openfly"
            else [str(Path(row["data_root"]) / row["images"]["mosaic"])]
        )
        previews = []
        for path in paths:
            with Image.open(path) as image:
                image = image.convert("RGB")
                image.thumbnail((256, 192))
                buf = io.BytesIO()
                image.save(buf, format="JPEG", quality=70)
                previews.append(
                    "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
                )
        cases.append(
            dict(
                id=identity,
                source=row["source"],
                group=row["group"],
                prompt=row["prompt"],
                previews=previews,
                image_sha256=row["image_sha256"],
                target=NAMES[row["action_id"]] if row["source"] == "openfly" else row["target"],
            )
        )
    write(VIEW / "joint_openfly_cases.json", cases)
    (VIEW / "joint_openfly.html").write_text(PAGE, encoding="utf-8")


def command(arguments, logfile, state, timeout):
    env = dict(
        os.environ,
        PYTHONPATH=str(ROOT / "src"),
        USE_TF="0",
        HF_HOME=str(BASE / "hf_cache"),
        TEMP=str(BASE / "tmp"),
        TMP=str(BASE / "tmp"),
    )
    (BASE / "tmp").mkdir(exist_ok=True)
    started = time.monotonic()
    with logfile.open("w", encoding="utf-8") as out:
        child = subprocess.Popen(
            [str(x) for x in arguments],
            cwd=ROOT,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            while child.poll() is None:
                snapshot(state)
                if time.monotonic() - started > timeout:
                    subprocess.run(
                        ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                        check=False,
                        capture_output=True,
                    )
                    raise TimeoutError("bounded child exceeded wall limit")
                time.sleep(10)
        finally:
            if child.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                )
        if child.returncode:
            raise RuntimeError(f"Child exited {child.returncode}; see {logfile}")


def main():
    os.chdir(ROOT)
    gallery()
    state = dict(status="preflight", active=None, completed=[])
    try:
        for model in MODELS:
            smoke = read(RUNS / f"{model}_joint_smoke_20260917_a/report.json")
            assert smoke and smoke["status"] == "complete" and smoke["reload_matches"], (
                model + " smoke gate"
            )
        for model in MODELS:
            assert not folder(model).exists(), "Do not overwrite or silently resume an existing run"
        for model in MODELS:
            state.update(status="training", active=model)
            limit = 10800 if model == "qwen" else 5400
            command(
                [
                    PYTHON,
                    "scripts/train_joint_openfly.py",
                    "--model",
                    model,
                    "--out",
                    folder(model),
                    "--max-wall-seconds",
                    limit,
                ],
                RUNS / f"{model}_joint_20260917_a.log",
                state,
                limit + 180,
            )
            result = read(folder(model) / "report.json")
            assert (
                result["status"] == "complete"
                and result["updates"] == 400
                and result["reload_matches"]
            )
            state.update(status="simulation_evaluation")
            flights = RUNS / f"{model}_joint_flights_20260917_a"
            command(
                [
                    PYTHON,
                    "scripts/evaluate_local_vla_pair.py",
                    "--model",
                    model,
                    "--label",
                    "mixed",
                    "--modes",
                    "trained",
                    "--data",
                    BASE / "data/public_goal_fixture_20260916_v1",
                    "--adapter",
                    folder(model) / "adapter_s400",
                    "--out",
                    flights,
                ],
                RUNS / f"{model}_joint_flights_20260917_a.log",
                state,
                1500,
            )
            command(
                [
                    PYTHON,
                    "scripts/audit_local_vla_pair.py",
                    "--runs",
                    flights,
                    "--modes",
                    "trained",
                    "--out",
                    REPORT / f"{model}_flight_audit.json",
                ],
                RUNS / f"{model}_joint_flight_audit.log",
                state,
                900,
            )
            from label_balanced_flights import label_page

            label_page(
                flights / "model_flights.html",
                VIEW / f"{model}_joint_flights.html",
                "Joint OpenFly + Local (D144)",
                model,
            )
            (REPORT / f"{model}_flight_browser").mkdir(exist_ok=True)
            command(
                [
                    sys.executable,
                    "scripts/check_local_vla_debugger.py",
                    "--runs",
                    flights,
                    "--url",
                    f"http://127.0.0.1:8771/{model}_joint_flights.html",
                    "--out",
                    REPORT / f"{model}_flight_browser",
                ],
                RUNS / f"{model}_joint_browser.log",
                state,
                600,
            )
            state["completed"].append(model)
        state.update(status="complete", active=None)
    except Exception as exc:
        state.update(status="failed", error=repr(exc))
        raise
    finally:
        snapshot(state)


PAGE = r"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Joint OpenFly + Local — three models</title>
<style>body{background:#0d1827;color:#e5edf7;font:16px system-ui;max-width:1250px;margin:24px auto;padding:0 18px}h1{font-size:28px}section{background:#17283b;padding:20px;border-radius:12px;margin:18px 0}a{color:#80c9ff}button,select{background:#263d56;color:white;padding:9px;border:1px solid #7291ac;max-width:100%}svg{width:100%;height:230px}p{line-height:1.5}.muted{color:#b2c1d3}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:9px;border-bottom:1px solid #435268}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:31%;margin-right:1%}.grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}@media(max-width:750px){.grid{grid-template-columns:1fr}td,th{padding:5px}}.ok{color:#8cdbb2}.bad{color:#ffb9a5}</style>
<h1>Joint OpenFly + Local · 256M / 500M / Qwen</h1><p>110 OpenFly source routes, 88 train / 22 validation. 2,929 native + 1,156 local training examples. Eight inconsistent source actions excluded. Both sources appear in every effective batch.</p><p class="muted">Bounded local pilots: 400 updates/model, fresh adapters, sequential GPU jobs. No AWS. OpenFly: 3m / 30° navigation primitives; local: velocity-bin JSON. These are separate, explicit instruction modes. OpenFly validation below is an offline diagnostic, not a flown benchmark.</p>
<section><strong id="status">Loading live status…</strong><p id="time" class="muted"></p><div id="models"></div></section>
<section><label>Model <select id="model"><option>smol256</option><option>smol500</option><option>qwen</option></select></label><h2>Loss curves</h2><div class="grid"><div><h3>Optimization loss</h3><div id="trainplot"></div><p class="muted">20-update moving average, separately by source. Changing examples and oversampled rare actions make individual steps noisy.</p></div><div><h3>Fixed-probe loss</h3><div id="valplot"></div><p class="muted">Identical examples, evaluation mode, at 0/100/200/300/400 updates. Solid: validation; dashed: training. Blue: local; orange: OpenFly. Lower is better within the same model/source.</p></div></div><div id="metrics"></div><div id="flights"></div></section>
<section><h2>Held-out observations and actual model output</h2><select id="case"></select><div id="images" style="margin-top:18px"></div><p id="target"></p><div id="outputs"></div><details><summary>Instruction and source provenance</summary><pre id="provenance"></pre></details><p class="muted">For OpenFly, three recorded views run oldest → current; the label refers to the current view's next primitive. These are source observations, not model-generated flight frames.</p></section>
<p><a href="openfly_clips.html">Source flight recordings</a> · <a href="expanded_models.html">Previous local-only comparison</a></p>
<script>
let data={}, cases=[];const $=id=>document.getElementById(id), esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function plot(series){let points=series.flatMap(s=>s.p);if(!points.length)return '<p class="muted">Pending measurements</p>';let ymax=Math.max(.1,...points.map(p=>p[1]))*1.08;let result='<svg viewBox="0 0 550 240" role="img" aria-label="Loss by optimizer update">';for(let i=0;i<=4;i++){let y=205-i*45;result+=`<line x1="45" x2="535" y1="${y}" y2="${y}" stroke="#3b5067"/><text x="0" y="${y+5}" fill="#bfd0e2" font-size="12">${(ymax*i/4).toFixed(2)}</text>`;}for(let i=0;i<=4;i++)result+=`<text x="${45+i*122.5}" y="225" fill="#bfd0e2" font-size="12">${i*100}</text>`;for(let s of series){let p=s.p.map(([x,y])=>`${45+x/400*490},${205-y/ymax*180}`).join(' ');result+=`<polyline points="${p}" fill="none" stroke="${s.color}" stroke-width="2" ${s.dash?'stroke-dasharray="5 4"':''}/>`;for(let [x,y] of s.p)if(s.p.length<10)result+=`<circle cx="${45+x/400*490}" cy="${205-y/ymax*180}" r="3" fill="${s.color}"/>`;}return result+'</svg>';}
function render(){const m=data.models?.[$('model').value]||{};$('status').textContent=`${data.state?.status||'waiting'} · ${data.state?.active||'no active job'}${data.state?.error?' · '+data.state.error:''}`;$('time').textContent=data.updated?'Snapshot: '+new Date(data.updated*1000).toLocaleString()+' · refreshes every 10 seconds':'';$('models').innerHTML=Object.entries(data.models||{}).map(([n,r])=>`<p><b>${esc(n)}</b>: ${esc(r.status)} · ${r.updates}/400 updates ${r.error?' · '+esc(r.error):''}</p>`).join('');let colors={local:'#7bc4ff',openfly:'#ffb469'};$('trainplot').innerHTML=plot(Object.entries(colors).map(([s,color])=>({color,p:(m.losses||[]).map((r,i,a)=>[r.step,a.slice(Math.max(0,i-19),i+1).reduce((v,x)=>v+x.domain_losses[s],0)/Math.min(i+1,20)])})));$('valplot').innerHTML=plot(Object.entries(colors).flatMap(([s,color])=>['val','train'].map(split=>({color,dash:split==='train',p:(m.comparable_losses||[]).map(r=>[r.step,r.values[s+':'+split]])}))));let metric='<h3>Frozen held-out predictions</h3><table><tr><th>Phase/source</th><th>Exact</th><th>Valid</th><th>False STOP</th><th>Macro recall</th></tr>';for(let [phase,sources] of Object.entries(m.metrics||{}))for(let [source,r] of Object.entries(sources))metric+=`<tr><td>${phase} / ${source}</td><td>${r.exact}/${r.n}</td><td>${r.valid}/${r.n}</td><td>${r.false_stop}</td><td>${r.macro_recall===undefined?'—':(r.macro_recall*100).toFixed(1)+'%'}</td></tr>`;$('metrics').innerHTML=metric+'</table><p class="muted">Native panel: 12/action, 72 total. Always-forward gives 12/72 exact and 16.7% macro recall. Exact local JSON match is stricter than successful flight. Invalid output remains a failure.</p>';$('flights').innerHTML=m.flight_ready?`<p><a href="${$('model').value}_joint_flights.html">Open ${$('model').value} actual local simulation flights</a></p>`:'<p class="muted">Actual model flights will appear after this model finishes training and evaluation.</p>';showCase();}
function action(x,source){if(x===null)return 'INVALID';return source==='openfly'?['STOP','forward 3m','left turn 30°','right turn 30°','up 3m','down 3m'][x]:JSON.stringify(x);}
function showCase(){let c=cases[$('case').value||0];if(!c)return;$('images').innerHTML=c.previews.map((p,i)=>`<img src="${p}" alt="Source observation ${i+1}">`).join('');$('target').textContent='Recorded target: '+(typeof c.target==='string'?c.target:JSON.stringify(c.target));let rows='';for(let [n,r] of Object.entries(data.models||{})){let p=r.after?.find(x=>x.id===c.id),b=r.before?.find(x=>x.id===c.id);rows+=`<p><b>${n}</b> · base: ${b?esc(action(b.parsed,c.source)):'pending'} · trained: <span class="${p?.exact?'ok':'bad'}">${p?esc(action(p.parsed,c.source)):'pending'}</span>${p?'<details><summary>Actual raw answer</summary><pre>'+esc(p.raw)+'</pre></details>':''}</p>`;}$('outputs').innerHTML=rows;$('provenance').textContent=JSON.stringify({id:c.id,prompt:c.prompt,image_sha256:c.image_sha256},null,2);}
async function refresh(){try{let text=await (await fetch('joint_openfly_status.json?t='+Date.now())).text();data=JSON.parse(text.replace(/("(?:\\.|[^"\\])*")|(-?Infinity|NaN)/g,(match,quoted)=>quoted??'null'));render();}catch(e){$('status').textContent='Waiting for training status: '+e.message;}}
$('model').onchange=render;$('case').onchange=showCase;fetch('joint_openfly_cases.json').then(r=>r.json()).then(c=>{cases=c;$('case').innerHTML=c.map((x,i)=>`<option value="${i}">${esc(x.source+' · '+x.group+' · '+x.id.slice(-90))}</option>`).join('');showCase();});refresh();setInterval(refresh,10000);
</script></html>"""


if __name__ == "__main__":
    main()
