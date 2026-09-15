"""Offline audit and visual report for the frozen context/action probe."""
import base64
import hashlib
import html
import json
from pathlib import Path

from PIL import Image

OUT = Path('reports/recovery_cycle_20260915/context_probe')
f = json.loads((OUT/'FREEZE.json').read_text())
rows=[]
cards=[]
for c in f['cases']:
    raw=json.loads((OUT/(c['id']+'.json')).read_text())
    assert 'error' not in raw, raw
    msg=raw['reply']['message']
    answer=json.loads(msg['thinking'])
    assert set(answer)==set(c['request']['format']['required'])
    assert answer['kind'] in ['target','exploration']
    assert all(type(answer[k]) is int and 0<=answer[k]<=999 for k in ['u','v'])
    assert all(m['digest']==f['model_digest'] for m in raw['residency']['models'])
    ids=[c['seq']] if c['mode']=='current_point' else [680,c['seq']]
    for seq,encoded in zip(ids,c['request']['messages'][0]['images'],strict=True):
        assert base64.b64decode(encoded)==(OUT/f'obs{seq}.png').read_bytes()
    im=Image.open(OUT/f"obs{c['seq']}.png").convert('RGB')
    u=round(answer['u']/999*(im.width-1))
    v=round(answer['v']/999*(im.height-1))
    action=answer.get('action','point')
    pixel=list(im.getpixel((u,v))) if action=='point' else None
    row=dict(case=c['id'],answer=answer,selected_current_pixel_rgb=pixel,
             current_absence_correct=answer['kind']=='exploration',wall_s=raw['wall_s'],
             source_sha256=hashlib.sha256((OUT/f"obs{c['seq']}.png").read_bytes()).hexdigest())
    rows.append(row)
    encoded=base64.b64encode((OUT/f"obs{c['seq']}.png").read_bytes()).decode()
    point=(f'<span class="point" style="left:{answer["u"]/9.99}%;'
           f'top:{answer["v"]/9.99}%"></span>') if action=='point' else ''
    cards.append(f'<article><h3>{html.escape(c["id"])}</h3><div class="image">'
                 f'<img src="data:image/png;base64,{encoded}">{point}</div>'
                 f'<b>{action}</b><pre>{html.escape(json.dumps(answer,indent=2))}</pre>'
                 f'<small>Current pixel RGB: {pixel}; '
                 f'inference {raw["wall_s"]:.2f}s</small></article>')
historical=base64.b64encode((OUT/'obs680.png').read_bytes()).decode()
page='''<!doctype html><meta charset="utf-8"><title>Recovery context and action probe</title>
<style>body{background:#0c1521;color:#d9e5f3;font:16px system-ui;margin:28px;max-width:1400px}
h1{font-size:25px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
article{background:#162638;border:1px solid #334a60;padding:18px;border-radius:10px}
.image{position:relative;width:224px;height:224px;margin:12px 0}img{width:224px}
.point{position:absolute;width:12px;height:12px;border:2px solid yellow;border-radius:50%;
transform:translate(-50%,-50%)}pre{white-space:pre-wrap;font-size:14px}small{color:#9bb1c7}
@media(max-width:900px){.grid{grid-template-columns:1fr}} </style>
<h1>Recovery: missing history or restricted action choice?</h1>
<p>Six local Qwen4 calls; two saved positions. No movement executed.</p>
<p>Both current images lack the target. History plus point output still points at gray obstacles.
History plus action choice selects <b>backtrack</b> twice. This is a diagnostic preference,
not demonstrated recovery or planning success. No target coordinates were supplied.</p>
<details><summary>Historical image supplied only in history conditions (obs680)</summary>
'''
page += f'<img src="data:image/png;base64,{historical}"></details><section class="grid">'
page += ''.join(cards)+'</section>'
Path('reports/debugger/recovery_context.html').write_text(page,encoding='utf-8')
(OUT/'RESULTS.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
