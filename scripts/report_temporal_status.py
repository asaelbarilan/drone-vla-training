"""Audit and show the three frozen status-only results; no model calls."""
import base64
import hashlib
import html
import json
from pathlib import Path

import jsonschema

from scripts.probe_recovery_context import read, write
from scripts.probe_temporal_status import OUT

f=read(OUT/'FREEZE.json')
rows=[]
cards=[]
for c in f['cases']:
    saved=read(OUT/(c['id']+'.json'))
    if 'error' in saved:
        rows.append(dict(case=c['id'],error=saved['error']))
        continue
    a=json.loads(saved['reply']['message']['thinking'])
    jsonschema.validate(a,c['request']['format'])
    for model in saved['residency']['models']:
        assert model['digest']==f['model_digest']
        assert model['size_vram']==0
    images=c['request']['messages'][0]['images']
    assert [hashlib.sha256(base64.b64decode(x)).hexdigest() for x in images]==c['image_hashes']
    g=c['grounding']
    expected='LOST' if c['seq']==1340 else 'CONTINUE'
    rows.append(dict(case=c['id'],answer=a,grounding=g,expected_for_flight_gate=expected,
        status_gate_pass=a['status']==expected,schema_valid=True,images_verified=len(images),
        cpu_only=True,wall_s=saved['wall_s']))
    point=(f'<span class="point" style="left:{g["u"]/9.99}%;'
           f'top:{g["v"]/9.99}%"></span>') if g['visible'] else ''
    cards.append(f'<article><h2>{c["id"]}</h2><div class="image">'
        f'<img src="data:image/png;base64,{images[-1]}">{point}</div>'
        f'<p>Current-only grounder: visible={g["visible"]}</p>'
        f'<p>Temporal status: <b>{a["status"]}</b></p>'
        f'<pre>{html.escape(a["evidence"])}</pre><details><summary>Exact history image</summary>'
        f'<img class="history" src="data:image/png;base64,{images[0]}"></details>'
        f'<details><summary>Exact prompt and supplied grounding</summary><pre>'
        f'{html.escape(c["request"]["messages"][0]["content"])}</pre></details></article>')
write(OUT/'RESULTS.json',rows)
page='''<!doctype html><html><head><meta charset="utf-8"><title>Separate temporal status probe</title>
<style>body{background:#0c1521;color:#d9e5f3;font:16px system-ui;margin:28px;max-width:1500px}
h1{font-size:26px}h2{font-size:18px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
article{background:#162638;border:1px solid #334a60;padding:18px;border-radius:10px}
.image{position:relative;width:224px;height:224px;margin:12px 0}.image img{width:224px}
.point{position:absolute;width:12px;height:12px;border:2px solid yellow;border-radius:50%;
transform:translate(-50%,-50%)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}
.history{max-width:100%;margin-top:10px}summary{cursor:pointer;padding:8px 0}
@media(max-width:900px){.grid{grid-template-columns:1fr}}</style></head><body>
<h1>Separate current grounding and temporal progress</h1>
<p>Three new CPU-only local Qwen3-VL4B calls. Saved current-only grounding is supplied unchanged.
The temporal answer can return only CONTINUE or LOST; it cannot locate targets or stop flight.</p>
<p>No movement executed. Status expectations are an experiment-entry criterion, not ground-truth
route feasibility. CPU placement and prompt differ from the earlier joint probe; this is not a
controlled measure of the architecture effect or flight latency.</p>
<section class="grid">'''+''.join(cards)+'</section></body></html>'
Path('reports/debugger/temporal_status.html').write_text(page,encoding='utf-8')
print(json.dumps(rows,indent=2))
