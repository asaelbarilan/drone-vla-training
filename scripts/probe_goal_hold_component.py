"""Hold one previously accepted semantic goal: execution fixture, no inference."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from scripts.probe_recovery_context import read, write
from scripts.probe_semantic_progress import ctx_for
from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import ControlCommand, MissionSpec, Trajectory, Vec3, WaypointGoal
from uavlab.core.frame_store import global_store
from uavlab.core.registry import REGISTRY

ROOT=Path('runs/c5_observed_view_return_20260915_s1061')
OUT=Path('reports/recovery_cycle_20260915/goal_hold_component')
START=51_000_000_000


def prepare():
 OUT.mkdir(parents=True,exist_ok=True)
 assert not (OUT/'FREEZE.json').exists(), 'Already frozen'
 m=read(ROOT/'manifest.json')
 events=[json.loads(x) for x in (ROOT/'events.jsonl').read_text().splitlines()]
 d=next(e for e in events if e['event_type']=='decision_proposed' and e['t_sim_ns']==START)
 plan=next(e for e in events if e['event_type']=='plan' and e['t_sim_ns']==START)
 assert plan['payload']['feasible'] and d['payload']['decision_payload']['target_label']=='target'
 calls=[read(p) for p in (ROOT/'debug/calls').glob('*.json')]
 c=next(c for c in calls if c['role']=='policy' and c['observation_seq']==1000)
 (OUT/'original_target_input.png').write_bytes((ROOT/c['image_files'][0]).read_bytes())
 write(OUT/'FREEZE.json',dict(source_run=ROOT.name,manifest=m,decision=d,plan=plan,
  events_sha256=hashlib.sha256((ROOT/'events.jsonl').read_bytes()).hexdigest(),
  start_ns=START,duration_s=20,replan_period_s=1,control_dt_s=.05,
  intervention='Retain the already accepted51s intermediate goal; repeat common planner at1Hz. '
  'No VLM or monitor, no waypoint replacement or global target steering. Common controller. '
  'This bypasses semantic freshness renewal for a bounded execution-only fixture, not a live profile.',
  criteria='Replay every original planner invocation in event order and match its points/feasibility. '
  'Match all prefix control poses and first branch command. Stop on collision or reaching the '
  'unchanged goal tolerance1m, else20s. Retain every result. Goal completion is not mission success. '
  'If prefix does not match, do not claim counterfactual execution evidence.'))
 print('Frozen20s hold component at51s; no model calls')


async def run():
 f=read(OUT/'FREEZE.json');m=f['manifest'];cfg=m['environment_config'];arch=m['architecture_config']
 assert hashlib.sha256((ROOT/'events.jsonl').read_bytes()).hexdigest()==f['events_sha256']
 mission=MissionSpec(mission_id='goal-hold-component',instruction=cfg['instruction'],
     task_family=cfg['task_family'],success=cfg['params']['success'],constraints=cfg['params']['constraints'])
 env=DeterministicEnv(**cfg['params']);await env.reset(mission,1061)
 planner=REGISTRY.build('planner',arch['planner']['name'],arch['planner']['params'])
 controller=REGISTRY.build('controller',arch['controller']['name'],arch['controller']['params'])
 planner.reset(mission,1061);controller.reset(mission,1061)
 events=[json.loads(x) for x in (ROOT/'events.jsonl').read_text().splitlines()]
 goals={e['trace_id']:WaypointGoal.model_validate(e['payload']['decision_payload'])
        for e in events if e['event_type']=='decision_proposed' and 'decision_payload' in e['payload']}
 obs=None;matched_plans=0;matched_poses=0;active=None
 for e in events:
  if e['t_sim_ns']>START:break
  p=e['payload']
  if e['event_type']=='control':
   if e['t_sim_ns']==START:break
   obs=await env.observe();matched_poses+=1
   assert obs.position.distance_to(Vec3(x=p['position_x'],y=p['position_y'],z=p['position_z']))<1e-7
   await env.step(ControlCommand(t_sim_ns=obs.t_sim_ns,
       velocity=Vec3(x=p['vx'],y=p['vy'],z=p['vz']),yaw_rate_rps=p['yaw_rate']),50_000_000)
  elif e['event_type']=='plan':
   ctx=ctx_for(obs,mission);ctx.t_sim_ns=e['t_sim_ns']
   proposed=planner.plan(goals[e['trace_id']],ctx)
   expected=Trajectory.model_validate(p['trajectory'])
   assert proposed.feasible==expected.feasible,(e['seq'],'feasibility')
   assert len(proposed.points)==len(expected.points),(e['seq'],'point count')
   assert all(a.position.distance_to(b.position)<1e-7 for a,b in zip(proposed.points,expected.points)), (e['seq'],'positions')
   matched_plans+=1
   if proposed.feasible:active=proposed
 assert matched_plans>0 and active is not None
 goal=WaypointGoal.model_validate(f['decision']['payload']['decision_payload'])
 prefix_audit=dict(poses_matched=matched_poses,plans_matched=matched_plans,
                   latest_observation_seq=obs.seq,branch_time_s=51)
 write(OUT/'PREFIX.json',prefix_audit)
 print('Prefix matched',prefix_audit,flush=True)
 rows=[];plans=[];outcome='timeout';first_match=False
 for tick in range(401):
  t=START+tick*50_000_000
  if tick>0 and tick%20==0:
   ctx=ctx_for(obs,mission);ctx.t_sim_ns=t
   candidate=planner.plan(goal,ctx)
   plans.append(dict(t=t/1e9,feasible=candidate.feasible,reason=candidate.reason,
                     metadata=candidate.metadata,points=[x.position.model_dump() for x in candidate.points]))
   if candidate.feasible:active=candidate
  obs=await env.observe();ctx=ctx_for(obs,mission)
  distance=obs.position.distance_to(goal.target)
  command=controller.track(active,ctx)
  if tick==0:
   original=next(e['payload'] for e in events if e['event_type']=='control' and e['t_sim_ns']==START)
   delta=command.velocity.distance_to(Vec3(x=original['vx'],y=original['vy'],z=original['vz']))
   assert delta<1e-7 and abs(command.yaw_rate_rps-original['yaw_rate'])<1e-7,('first command',delta,command.yaw_rate_rps,original['yaw_rate'])
   first_match=True
  row=dict(t=t/1e9,position=obs.position.model_dump(),yaw=obs.yaw_rad,
           distance_to_stored_goal_m=distance,velocity=command.velocity.model_dump())
  if tick%20==0 or distance<=goal.tolerance_m or tick==400:
   path=OUT/f'view_{tick:03d}.png';global_store().get(obs.rgb.uri).save(path);row['image']=path.name
  rows.append(row)
  if env.status().collided:outcome='collision';break
  if distance<=goal.tolerance_m:outcome='intermediate_goal_reached';break
  if tick==400:break
  await env.step(command,50_000_000)
 result=dict(type='saved-state execution component, no model flight',prefix=prefix_audit,
  first_command_matched=first_match,outcome=outcome,goal=goal.model_dump(mode='json'),
  start_distance_m=rows[0]['distance_to_stored_goal_m'],final_distance_m=distance,
  closest_distance_m=min(r['distance_to_stored_goal_m'] for r in rows),
  collision_count=env.status().collision_count,min_obstacle_distance_m=env.status().min_obstacle_distance_m,
  elapsed_s=(obs.t_sim_ns-START)/1e9,rows=rows,plans=plans,
  obstacles=[dict(center=o.center.tolist(),half=o.half.tolist()) for o in env.obstacles])
 write(OUT/'RESULT.json',result)
 print(json.dumps({k:v for k,v in result.items() if k not in ['rows','plans','obstacles']},indent=2))


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run']);mode=p.parse_args().mode
 prepare() if mode=='prepare' else asyncio.run(run())
