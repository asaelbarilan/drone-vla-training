"""Three status-only temporal calls with frozen independent current grounding."""
import argparse
import json
import time
from pathlib import Path

from scripts.probe_recovery_context import read, request, write

OUT=Path('reports/recovery_cycle_20260915/status_probe')
SOURCE=Path('reports/recovery_cycle_20260915/semantic_probe')


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'FREEZE.json').exists(), 'Already frozen'
    f=read(SOURCE/'FREEZE.json')
    results={r['case']:r for r in read(SOURCE/'RESULTS.json')}
    cases=[]
    for c in f['cases']:
        if c['mode']!='semantic':
            continue
        seq=c['seq']
        grounding=results[f'obs{seq}_legacy']['parsed']
        prompt=(
            'Mission: fly to the red tower and stop there. Judge only whether the visual '
            'navigation sequence supports CONTINUE or LOST. You cannot authorize STOP, '
            'choose coordinates, or redefine target visibility. Image 1 is a labeled '
            'chronological HISTORY sheet. Image 2 is the full-resolution CURRENT image. '
            'The separate current-image grounder has already inspected ONLY image 2; '
            'its timestamped result is evidence you must preserve. Historical target '
            'sightings are never current sightings. '
            f'Current time={(seq-1)*.05:.2f}s, observation={seq}. '
            f'Current-only grounding={json.dumps(grounding)}. '
            f'History panel times in seconds={[round((x-1)*.05,2) for x in c["history_seqs"]]}. '
            'Return CONTINUE if visual history and the current view support coherent '
            'exploration or a plausible continuing detour. A briefly occluded target alone '
            'does not prove route failure. Return LOST if the sequence indicates drift, '
            'repeated unsuccessful movement, or loss of a useful route. Do not assume '
            'an invisible destination remains ahead or that a narrow passage is traversable. '
            'When the target is currently visible, ordinary approach can continue; '
            'arrival is decided elsewhere. Give a short evidence phrase about current '
            'visibility and temporal progress. Return JSON with evidence,status only.'
        )
        body=dict(model='qwen3-vl:4b',messages=[dict(role='user',content=prompt,
            images=c['request']['messages'][0]['images'])],stream=False,think=False,
            format=dict(type='object',properties=dict(evidence=dict(type='string',maxLength=180),
                status=dict(type='string',enum=['CONTINUE','LOST'])),
                required=['evidence','status'],additionalProperties=False),keep_alive='10m',
            options=dict(temperature=0,seed=0,num_ctx=8192,num_predict=192,num_gpu=0))
        cases.append(dict(id=f'obs{seq}_status',seq=seq,grounding=grounding,
            grounding_source=f'../semantic_probe/obs{seq}_legacy.json',
            image_hashes=c['image_hashes'],request=body))
    write(OUT/'FREEZE.json',dict(cases=cases,max_calls=3,retries=0,model_digest=f['model_digest'],
        hardware='CPU-only dedicated11435 while Valley is running; not flight latency benchmark',
        criteria='All attempts retained. Valid evidence/status only, no STOP/coordinates/visibility '
        'authority. Evidence must respect supplied current grounding. To justify a flight '
        'hypothesis, CONTINUE on visible and first-occlusion cases and LOST on prolonged '
        'loss with visually consistent evidence. This is an experiment-entry criterion, '
        'not ground-truth route feasibility. If no distinction or contradictory evidence, '
        'do not run a flight or tune these same cases repeatedly. Reused grounding is '
        'diagnostic only; live execution must charge both calls/latencies.'))
    print('Frozen3 status-only calls; no runtime change')


def run():
    f=read(OUT/'FREEZE.json')
    assert any(m['name']=='qwen3-vl:4b' and m['digest']==f['model_digest']
               for m in request('/api/tags')['models'])
    for c in f['cases']:
        marker=OUT/(c['id']+'.attempt.json')
        assert not marker.exists(), 'No retry: '+c['id']
        write(marker,dict(started=time.time()))
        start=time.monotonic()
        try:
            result=dict(reply=request('/api/chat',c['request']),residency=request('/api/ps'))
        except Exception as exc:
            result=dict(error=str(exc))
        result.update(case=c['id'],wall_s=time.monotonic()-start)
        write(OUT/(c['id']+'.json'),result)
        print(c['id'],result.get('reply',{}).get('message',{}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['prepare','run'])
    mode=p.parse_args().mode
    prepare() if mode=='prepare' else run()
