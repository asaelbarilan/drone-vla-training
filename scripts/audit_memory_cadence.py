"""Audit actual recorded memory-update cadence without inference or flight changes."""
import asyncio
import base64
import json
from pathlib import Path

from scripts.probe_recovery_context import read, write
from scripts.probe_semantic_progress import ctx_for
from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import ControlCommand, MissionSpec, Vec3
from uavlab.core.frame_store import global_store
from uavlab.plugins.reasoning.onfly import OnFlyHybridMemory, _history_sheet, _ONFLY_VISUALS

OUT=Path('reports/recovery_cycle_20260915/memory_cadence')
ROOT=Path('runs/c5_clutter_qwen4_20260915_s1061')


async def main():
 OUT.mkdir(exist_ok=True)
 m=read(ROOT/'manifest.json');cfg=m['environment_config']
 mission=MissionSpec(mission_id='memory-cadence',instruction=cfg['instruction'],
     task_family=cfg['task_family'],success=cfg['params']['success'],constraints=cfg['params']['constraints'])
 env=DeterministicEnv(**cfg['params']);await env.reset(mission,1061)
 memory=OnFlyHybridMemory(**m['architecture_config']['memory']['params']);memory.reset(mission,1061)
 updates=0;poses=0;cases=[];obs=None
 for line in (ROOT/'events.jsonl').read_text().splitlines():
  e=json.loads(line);p=e['payload']
  if e['event_type']=='control':
   obs=await env.observe();poses+=1
   assert obs.position.distance_to(Vec3(x=p['position_x'],y=p['position_y'],z=p['position_z']))<1e-7
   await env.step(ControlCommand(t_sim_ns=obs.t_sim_ns,
       velocity=Vec3(x=p['vx'],y=p['vy'],z=p['vz']),yaw_rate_rps=p['yaw_rate']),50_000_000)
  elif e['event_type']=='perception':
   assert obs.seq==p['observation_seq']
  elif e['event_type']=='memory_update':
   memory.update(obs,ctx_for(obs,mission).perception,None)
   snap=memory.snapshot();updates+=1
   assert len(snap.items)==p['items'], (e['t_sim_ns'],len(snap.items),p['items'])
   if obs.seq in [680,720,1340]:
    history=[x for x in snap.items if x.observation_seq<obs.seq]
    _history_sheet([_ONFLY_VISUALS[x.image_uri] for x in history]).save(OUT/f'obs{obs.seq}_actual_history.png')
    global_store().get(obs.rgb.uri).save(OUT/f'obs{obs.seq}_current.png')
    cases.append(dict(seq=obs.seq,current_s=obs.t_sim_ns/1e9,
         history_seqs=[x.observation_seq for x in history],
         history_times_s=[x.t_sim_ns/1e9 for x in history],
         gap_s=(obs.t_sim_ns-max(x.t_sim_ns for x in history))/1e9))
    if obs.seq==1340:break
 write(OUT/'RESULT.json',dict(poses_matched=poses,memory_item_counts_matched=updates,cases=cases,
     correction='D118/D119 supplied densely sampled constructed history, not exact runtime memory. '
     'Current source images and recorded responses remain exact. No model re-runs.'))
 print(json.dumps(read(OUT/'RESULT.json'),indent=2))


if __name__=='__main__':asyncio.run(main())
