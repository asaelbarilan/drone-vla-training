"""Render and audit all frozen semantic monitor attempts; no new inference."""
import base64
import hashlib
import html
import json
from pathlib import Path

import jsonschema
from PIL import Image, ImageDraw

from scripts.probe_semantic_progress import OUT
from scripts.probe_recovery_context import read, write

f=read(OUT/'FREEZE.json')
rows=read(OUT/'RESULTS.json')
cards=[]
checks=[]
for c,r in zip(f['cases'],rows,strict=True):
    assert c['id']==r['case']
    saved=read(OUT/(c['id']+'.json'))
    assert 'error' not in saved
    jsonschema.validate(r['parsed'],c['request']['format'])
    assert all(m['digest']==f['model_digest'] for m in saved['residency']['models'])
    inputs=c['request']['messages'][0]['images']
    for i,encoded in enumerate(inputs):
        raw=base64.b64decode(encoded)
        assert hashlib.sha256(raw).hexdigest()==c['image_hashes'][i]
        assert raw==(OUT/f"{c['id']}_input{i}.png").read_bytes()
    current=inputs[-1]
    answer=r['parsed']
    visible=answer['visible']
    expected_visible=c['seq']==680
    identity_ok=visible==expected_visible
    pixel=r['rgb_point']
    if expected_visible:
        identity_ok=identity_ok and pixel is not None and pixel[0]>pixel[1]*1.5
    assert r['accepted']!='stop'
    checks.append(dict(case=c['id'],json_schema_valid=True,current_identity_correct=identity_ok,
                       input_hashes_matched=len(inputs),accepted_stop=False))
    point=(f'<span class="point" style="left:{answer["u"]/9.99}%;'
           f'top:{answer["v"]/9.99}%"></span>') if visible else ''
    history=(f'<details><summary>Exact HISTORY input</summary>'
             f'<img class="history" src="data:image/png;base64,{inputs[0]}"></details>') \
             if len(inputs)>1 else ''
    cards.append(f'<article data-case="{c["id"]}"><h2>{c["id"]}</h2>'
        f'<b class="{"pass" if identity_ok else "fail"}">'
        f'Current identity: {"correct" if identity_ok else "FAILED"}</b>'
        f'<div class="image"><img src="data:image/png;base64,{current}">{point}</div>'
        f'<p>Raw status: {answer.get("status","visibility rule")} → '
        f'accepted: {r["accepted"].upper()}</p>'
        f'<p>Selected current pixel RGB: {pixel}</p>'
        f'<pre>{html.escape(json.dumps(answer,indent=2,ensure_ascii=False))}</pre>'
        f'{history}<details><summary>Exact prompt</summary><pre>'
        f'{html.escape(c["request"]["messages"][0]["content"])}</pre></details>'
        f'<details><summary>Runtime stopping checks</summary><pre>'
        f'{html.escape(r["evidence"])}</pre></details></article>')
write(OUT/'AUDIT.json',dict(cases=checks,poses_matched=f['poses_matched'],
                          independent_case_state=f['initial_monitor_state'],
                          gate='FAIL: do not promote to flight'))
page='''<!doctype html><html><head><meta charset="utf-8"><title>Semantic monitor probe</title>
<style>body{background:#0c1521;color:#d9e5f3;font:16px system-ui;margin:28px;max-width:1400px}
h1{font-size:26px}h2{font-size:18px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
article{background:#162638;border:1px solid #334a60;padding:18px;border-radius:10px}
.image{position:relative;width:224px;height:224px;margin:12px 0}.image img{width:224px}
.point{position:absolute;width:12px;height:12px;border:2px solid yellow;border-radius:50%;
transform:translate(-50%,-50%)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}
.history{max-width:100%;margin-top:10px}.pass{color:#67d4bf}.fail{color:#ff9e98}
summary{cursor:pointer;padding:8px 0}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>
</head><body><h1>History-based progress monitor: saved-frame gate failed</h1>
<p>Six local Qwen3-VL4B calls. No new flight. Left: legacy current image. Right: history + current image.</p>
<p>The candidate imports historical target visibility into the current frame at35.95s and points
at a gray wall. At33.95s its point misses the visible red body. Both variants reject the absent
target at66.95s. Runtime distance/confirmation guards prevent every requested STOP in this probe.</p>
<p>These are three selected diagnostic cases, not a navigation benchmark. Each starts acquired,
without confirmed arrival memory. 1,340 replay poses and all three source RGB images matched.
The candidate stays disabled. No route-traversability conclusion follows from these images.</p>
<p style="border:2px solid #ffb76b;padding:12px"><b>D-120 correction:</b> History in these calls was constructed at control cadence, not exact live memory cadence. Current RGB and replies are exact. Actual live history at35.95s includes34.95s (1s gap); the earlier8.1s live-gap claim is withdrawn. No model reruns.</p><section class="grid">'''+''.join(cards)+'</section></body></html>'
Path('reports/debugger/semantic_progress.html').write_text(page,encoding='utf-8')
sheet=Image.new('RGB',(672,520),'white')
draw=ImageDraw.Draw(sheet)
for j,r in enumerate(rows):
    seq=f['cases'][j]['seq']
    x=(j//2)*224
    y=(j%2)*260
    im=Image.open(OUT/f'obs{seq}.png').convert('RGB')
    a=r['parsed']
    if a['visible']:
        u=round(a['u']/999*223);v=round(a['v']/999*223)
        ImageDraw.Draw(im).ellipse((u-5,v-5,u+5,v+5),outline='yellow',width=2)
    sheet.paste(im,(x,y+30))
    draw.text((x+3,y+4),r['case'],fill='black')
sheet.save(OUT/'POINTS.png')
print(json.dumps(checks,indent=2))
