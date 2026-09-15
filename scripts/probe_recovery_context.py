"""Six frozen saved-view calls: current point, history point, history action diagnosis."""
import argparse
import base64
import hashlib
import json
import math
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path('reports/recovery_cycle_20260915/context_probe')
ROOT = Path('runs/c5_recovery_fresh_20260915_s1061')
HOST = 'http://127.0.0.1:11435'
# Full installed digest is verified from the frozen flight configuration below.


def write(path, data):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def request(path, body=None):
    req = urllib.request.Request(HOST + path, data=None if body is None else
                                 json.dumps(body).encode(),
                                 headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'FREEZE.json').exists():
        raise RuntimeError('Already frozen')
    calls = [read(p) for p in (ROOT/'debug/calls').glob('*.json')]
    calls = {c['observation_seq']:c for c in calls
             if c['role']=='policy' and c['status']=='complete'}
    events = [json.loads(x) for x in (ROOT/'events.jsonl').read_text().splitlines()]
    decisions = {e['payload']['source_observation_seq']:e['payload'] for e in events
                 if e['event_type']=='decision_proposed'
                 and 'source_observation_seq' in e['payload']}
    cfg = read(Path('reports/recovery_cycle_20260915/CYCLE1_FREEZE.json'))
    images = {}
    for seq in [680, 800, 920]:
        raw = (ROOT/calls[seq]['image_files'][0]).read_bytes()
        (OUT/f'obs{seq}.png').write_bytes(raw)
        images[seq] = dict(sha256=hashlib.sha256(raw).hexdigest(),
                           base64=base64.b64encode(raw).decode())
    cases = []
    for seq in [800, 920]:
        c = calls[seq]
        old = decisions[680]['provenance']
        now = decisions[seq]['provenance']
        delta = [float(now['source_position_'+k])-float(old['source_position_'+k])
                 for k in ['x','y','z']]
        yaw_delta = math.degrees(float(now['source_yaw_rad'])-float(old['source_yaw_rad']))
        context = (
            'There are two images. Image 1 is a historical frame when the policy last '
            'identified the red target. Image 2 is the CURRENT camera image. Return points '
            'only in image 2 coordinates. Historical visibility is not current visibility. '
            f'Since image 1, onboard odometry translation in east,north,up metres is '
            f'{[round(x,2) for x in delta]}, and yaw change is {yaw_delta:.1f} degrees. '
            'The monitor subsequently reported LOST. Use history to understand the lost '
            'target and current occlusion; do not assume a hidden passage is traversable. '
        )
        for mode in ['current_point', 'history_point', 'history_action']:
            schema = c['response_schema']
            prompt = c['prompt']
            img = [images[seq]['base64']]
            if mode != 'current_point':
                prompt = context + prompt
                img.insert(0, images[680]['base64'])
            if mode == 'history_action':
                prompt = context + (
                    'Mission: fly to the red tower and stop there. This is a diagnosis only; '
                    'no action will execute. Decide what you need to do NEXT to recover visual '
                    'contact. Choose action=point only if moving toward a CURRENT image point '
                    'is your preferred next step; otherwise choose turn_left, turn_right, '
                    'backtrack, or hold. Left/right are relative to current camera. Do not '
                    'claim current visibility based on the historical image. Return JSON '
                    'with evidence describing current objects and your reason, action, '
                    'kind (target if currently visible, otherwise exploration), u,v. '
                    'For point use integer current-image coordinates 0..999, top-left origin; '
                    'for every other action use u=v=0. No hidden goal coordinates are available.'
                )
                schema = json.loads(json.dumps(schema))
                schema['properties']['action'] = dict(type='string', enum=[
                    'point','turn_left','turn_right','backtrack','hold'])
                schema['required'].append('action')
            body = dict(model='qwen3-vl:4b', messages=[dict(role='user',content=prompt,images=img)],
                        stream=False, think=False, format=schema, keep_alive='10m',
                        options=dict(temperature=0,seed=0,num_ctx=8192,num_predict=192))
            cases.append(dict(id=f'obs{seq}_{mode}',seq=seq,mode=mode,request=body))
    write(OUT/'FREEZE.json',dict(cases=cases,model_digest=cfg['architecture']['inference']
                                ['params']['expected_digest'],max_calls=6,retries=0,
          criteria='All six attempts retained. Check JSON/current absence and whether point lies '
                   'on obstacle face. Compare choices within each pair of saved positions. '
                   'Nonpoint actions are diagnostic only, not implemented. No success/flight '
                   'promotion from this probe; no oracle target direction supplied.'))
    sheet = Image.new('RGB',(672,250),'white')
    for i,seq in enumerate([680,800,920]):
        sheet.paste(Image.open(OUT/f'obs{seq}.png'),(i*224,24))
        ImageDraw.Draw(sheet).text((i*224+3,3),f'obs{seq}',fill='black')
    sheet.save(OUT/'INPUTS.png')
    print('Frozen six calls on two saved positions plus historical obs680')


def run():
    f = read(OUT/'FREEZE.json')
    tags = request('/api/tags')['models']
    assert any(m['name']=='qwen3-vl:4b' and m['digest']==f['model_digest'] for m in tags)
    for c in f['cases']:
        marker = OUT/(c['id']+'.attempt.json')
        if marker.exists():
            raise RuntimeError('No retry permitted: '+c['id'])
        write(marker,dict(started=time.time()))
        start = time.monotonic()
        try:
            reply = request('/api/chat',c['request'])
            record = dict(case=c['id'],reply=reply,wall_s=time.monotonic()-start,
                          residency=request('/api/ps'))
        except Exception as exc:
            record = dict(case=c['id'],error=str(exc),wall_s=time.monotonic()-start)
        write(OUT/(c['id']+'.json'),record)
        print(c['id'], record.get('reply',{}).get('message',{}), flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['prepare','run'])
    mode=parser.parse_args().mode
    prepare() if mode=='prepare' else run()
