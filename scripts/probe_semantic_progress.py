"""Frozen monitor visibility/progress ablation on replayed baseline source frames."""
import argparse
import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from scripts.probe_recovery_context import read, request, write
from tests.unit.test_onfly import StubModel, services
from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import ControlCommand, MemorySnapshot, MissionSpec, ObservationPacket
from uavlab.contracts import PerceptionState, Vec3
from uavlab.core.frame_store import global_store
from uavlab.core.services import bind
from uavlab.interfaces import DecisionContext
from uavlab.plugins.reasoning.onfly import OnFlyHybridMemory, OnFlyMonitor

OUT=Path('reports/recovery_cycle_20260915/semantic_probe')
ROOT=Path('runs/c5_clutter_qwen4_20260915_s1061')
SEQS=[680,720,1340]


def ctx_for(obs, mission, memory=None):
    return DecisionContext(mission=mission,observation=obs,
        perception=PerceptionState(observation_seq=obs.seq,t_sim_ns=obs.t_sim_ns),
        memory=memory or MemorySnapshot(observation_seq=obs.seq,t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,t_wall_ns=0,episode_id='semantic-probe')


async def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'FREEZE.json').exists(), 'Already frozen'
    manifest=read(ROOT/'manifest.json')
    cfg=manifest['environment_config']
    arch=manifest['architecture_config']
    mission=MissionSpec(mission_id='semantic-probe',instruction=cfg['instruction'],
        task_family=cfg['task_family'],success=cfg['params']['success'],
        constraints=cfg['params']['constraints'])
    env=DeterministicEnv(**cfg['params'])
    await env.reset(mission,1061)
    memory=OnFlyHybridMemory(**arch['memory']['params'])
    memory.reset(mission,1061)
    calls={c['observation_seq']:c for p in (ROOT/'debug/calls').glob('*.json')
           if (c:=read(p))['role']=='policy' and c['status']=='complete'}
    controls=[e for line in (ROOT/'events.jsonl').read_text().splitlines()
              if (e:=json.loads(line))['event_type']=='control']
    cases=[]
    poses=0
    for e in controls:
        obs=await env.observe()
        p=e['payload']
        assert obs.position.distance_to(Vec3(x=p['position_x'],y=p['position_y'],
                                            z=p['position_z']))<1e-7
        poses+=1
        ctx=ctx_for(obs,mission)
        memory.update(obs,ctx.perception,None)
        ctx.memory=memory.snapshot()
        if obs.seq in SEQS:
            seq=obs.seq
            rgb=global_store().get(obs.rgb.uri)
            original=(ROOT/calls[seq]['image_files'][0]).read_bytes()
            assert np.array_equal(np.asarray(rgb),np.asarray(Image.open(io.BytesIO(original))))
            (OUT/f'obs{seq}.png').write_bytes(original)
            np.save(OUT/f'obs{seq}_depth.npy',global_store().get(obs.depth.uri))
            write(OUT/f'obs{seq}.json',obs.model_dump(mode='json'))
            for semantic in [False,True]:
                mode='semantic' if semantic else 'legacy'
                reply=dict(evidence='capture fixture',visible=False,u=None,v=None)
                if semantic:
                    reply['status']='CONTINUE'
                stub=StubModel([json.dumps(reply)])
                monitor=OnFlyMonitor(**arch['monitor']['params'],semantic_progress=semantic)
                monitor.reset(mission,1061)
                monitor._ever_acquired=True
                bind(monitor,services(stub))
                await monitor.assess(ctx)
                r=stub.requests[0]
                body=dict(model='qwen3-vl:4b',messages=[dict(role='user',content=r.prompt,
                          images=list(r.images))],stream=False,think=False,
                          format=r.response_schema,keep_alive='10m',
                          options=dict(temperature=0,seed=0,num_ctx=8192,num_predict=192))
                for i,encoded in enumerate(r.images):
                    (OUT/f'obs{seq}_{mode}_input{i}.png').write_bytes(base64.b64decode(encoded))
                assert np.array_equal(np.asarray(Image.open(io.BytesIO(
                    base64.b64decode(r.images[-1])))),np.asarray(rgb))
                cases.append(dict(id=f'obs{seq}_{mode}',seq=seq,mode=mode,request=body,
                    image_hashes=[hashlib.sha256(base64.b64decode(x)).hexdigest() for x in r.images],
                    history_seqs=[x.observation_seq for x in ctx.memory.items
                                  if x.observation_seq<seq]))
            print('Prepared',seq,flush=True)
        if obs.seq>=max(SEQS):
            break
        await env.step(ControlCommand(t_sim_ns=obs.t_sim_ns,
            velocity=Vec3(x=p['vx'],y=p['vy'],z=p['vz']),yaw_rate_rps=p['yaw_rate']),50_000_000)
    assert len(cases)==6
    write(OUT/'FREEZE.json',dict(cases=cases,max_calls=6,retries=0,
        model_digest=arch['inference']['params']['expected_digest'],
        monitor_params=arch['monitor']['params'],mission=mission.model_dump(mode='json'),
        poses_matched=poses,current_images_matched=3,
        initial_monitor_state='ever_acquired=true; no confirmed arrival memory; independent cases',
        criteria='Six attempts, no retries. JSON/status valid; current visibility true only obs680; '
        'point must hit red body when visible. No accepted STOP in these distant/absent scenes. '
        'Inspect semantic CONTINUE vs LOST across first and sustained occlusion. '
        'No oracle route labels are given. A short-occlusion CONTINUE is a candidate hypothesis, '
        'not proof of traversability. Runtime defaults stay legacy. No flight promotion if '
        'identity fails or semantic outputs provide no useful distinction.'))
    sheet=Image.new('RGB',(672,248),'white')
    for i,seq in enumerate(SEQS):
        sheet.paste(Image.open(OUT/f'obs{seq}.png'),(224*i,24))
        ImageDraw.Draw(sheet).text((224*i+4,5),f'obs{seq} t={(seq-1)*.05:.2f}s',fill='black')
    sheet.save(OUT/'CURRENT_INPUTS.png')


def run():
    import time
    f=read(OUT/'FREEZE.json')
    assert any(m['name']=='qwen3-vl:4b' and m['digest']==f['model_digest']
               for m in request('/api/tags')['models'])
    for c in f['cases']:
        marker=OUT/(c['id']+'.attempt.json')
        assert not marker.exists(), 'No retries: '+c['id']
        write(marker,dict(started=time.time()))
        start=time.monotonic()
        try:
            result=dict(reply=request('/api/chat',c['request']),residency=request('/api/ps'))
        except Exception as exc:
            result=dict(error=str(exc))
        result.update(case=c['id'],wall_s=time.monotonic()-start)
        write(OUT/(c['id']+'.json'),result)
        print(c['id'],result.get('reply',{}).get('message',{}),flush=True)


async def report():
    f=read(OUT/'FREEZE.json')
    rows=[]
    for c in f['cases']:
        saved=read(OUT/(c['id']+'.json'))
        message=saved.get('reply',{}).get('message',{})
        raw=message.get('thinking','')
        obs=ObservationPacket.model_validate(read(OUT/f"obs{c['seq']}.json"))
        rgb=Image.open(OUT/f"obs{c['seq']}.png").convert('RGB')
        global_store().put(obs.rgb.uri,rgb)
        global_store().put(obs.depth.uri,np.load(OUT/f"obs{c['seq']}_depth.npy"))
        mission=MissionSpec.model_validate(f['mission'])
        monitor=OnFlyMonitor(**f['monitor_params'],semantic_progress=c['mode']=='semantic')
        monitor.reset(mission,1061)
        monitor._ever_acquired=True
        bind(monitor,services(StubModel([raw])))
        state=await monitor.assess(ctx_for(obs,mission))
        try:
            parsed=json.loads(raw)
        except ValueError:
            parsed={}
        rgb_point=None
        if parsed.get('visible') and type(parsed.get('u')) is int and type(parsed.get('v')) is int:
            x=round(parsed['u']/999*(rgb.width-1))
            y=round(parsed['v']/999*(rgb.height-1))
            if 0<=x<rgb.width and 0<=y<rgb.height:
                rgb_point=rgb.getpixel((x,y))
        rows.append(dict(case=c['id'],parsed=parsed,accepted=state.label.value,
                         evidence=state.evidence,rgb_point=rgb_point,wall_s=saved['wall_s']))
    write(OUT/'RESULTS.json',rows)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['prepare','run','report'])
    mode=p.parse_args().mode
    run() if mode=='run' else asyncio.run(prepare() if mode=='prepare' else report())
