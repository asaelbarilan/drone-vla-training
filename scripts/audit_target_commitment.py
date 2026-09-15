"""Audit explicit target-execution leases in a completed flight; no inference."""
import json
from pathlib import Path

from scripts.probe_recovery_context import read, write

NAME='c5_target_commitment_20260915_s1061'
ROOT=Path('runs')/NAME
OUT=Path('reports/recovery_cycle_20260915/cycle3')


def events(root):
 return [json.loads(x) for x in (root/'events.jsonl').read_text().splitlines()]


def main():
 OUT.mkdir(exist_ok=True)
 es=events(ROOT)
 decisions={e['trace_id']:e for e in es if e['event_type']=='decision_proposed'
            and 'source_observation_seq' in e['payload']}
 accepted={e['trace_id'] for e in es if e['event_type']=='decision_executed'}
 plans=[e for e in es if e['event_type']=='plan'
        and 'target_commitment_source_id' in e['payload'].get('planner_metadata',{})]
 controls=[e for e in es if e['event_type']=='control']
 leases={};errors=[]
 for e in plans:
  m=e['payload']['planner_metadata'];owner=m['target_commitment_source_id']
  origin=decisions[owner];d=origin['payload']
  source_t=origin['t_sim_ns']/1e9-d['production_latency_s']
  deadline=int(m['target_commitment_deadline_ns'])/1e9
  if owner not in accepted or d['provenance'].get('waypoint_kind')!='target':
   errors.append(['unaccepted_target_owner',e['seq']])
  if abs(int(m['target_commitment_source_t_ns'])/1e9-source_t)>1e-8:
   errors.append(['source_time_changed',e['seq']])
  if int(m['target_commitment_source_seq'])!=d['source_observation_seq']:
   errors.append(['source_sequence_changed',e['seq']])
  if owner in leases and leases[owner]['deadline_s']!=deadline:
   errors.append(['deadline_renewed',e['seq']])
  leases.setdefault(owner,dict(source_t_s=source_t,source_seq=d['source_observation_seq'],
      activation_s=deadline-20,deadline_s=deadline,plan_times=[],plan_failures=[]))
  leases[owner]['plan_times'].append(e['t_sim_ns']/1e9)
  if not e['payload']['feasible']:leases[owner]['plan_failures'].append(e['t_sim_ns']/1e9)
  if e['trace_id'] in accepted:
   errors.append(['deferred_exploration_marked_executed',e['seq']])
 old_commands=[]
 for e in controls:
  p=e['payload'];owner=e['trace_id'];age=p.get('decision_age_s')
  if age is None or age<=4+1e-8:continue
  lease=leases.get(owner);t=e['t_sim_ns']/1e9
  if lease is None or not lease['activation_s']<=t<lease['deadline_s']:
   errors.append(['old_command_outside_lease',e['seq'],t,owner])
  elif abs(age-(t-lease['source_t_s']))>1e-8 or p['source_observation_seq']!=lease['source_seq']:
   errors.append(['old_command_provenance_changed',e['seq']])
  old_commands.append(dict(t=t,source_id=owner,age_s=age))
 monitors=[e for e in es if e['event_type']=='monitor'
           and e['payload'].get('target_commitment_deferred_lost')]
 recovery_times={e['t_sim_ns'] for e in es if e['event_type']=='recovery_trigger'
                 and e['payload'].get('trigger')=='onfly_lost'}
 for e in monitors:
  if e['payload']['label']!='lost' or e['t_sim_ns'] in recovery_times:
   errors.append(['lost_label_or_arbitration',e['seq']])
 comparisons=[]
 for name in ['c5_clutter_qwen4_20260915_s1061','c5_recovery_fresh_20260915_s1061']:
  base=[e for e in events(Path('runs')/name) if e['event_type']=='control']
  first=None
  fields=['position_x','position_y','position_z','vx','vy','vz','yaw_rate']
  for a,b in zip(base,controls):
   if a['t_sim_ns']!=b['t_sim_ns'] or any(abs(a['payload'][k]-b['payload'][k])>1e-8 for k in fields):
    first=b['t_sim_ns']/1e9;break
  comparisons.append(dict(baseline=name,first_different_control_s=first))
 report=dict(leases=leases,old_source_commands=len(old_commands),
  max_original_source_age_s=max((x['age_s'] for x in old_commands),default=0),
  deferred_lost_events=len(monitors),deferred_lost_times_s=[e['t_sim_ns']/1e9 for e in monitors],
  recovery_times_s=sorted(t/1e9 for t in recovery_times),prefix_comparisons=comparisons,
  violations=errors,notes='CPU/GPU placement differs; comparisons inspect realized prefix, '
  'not formal deterministic equivalence. STOP remains separately evaluated by runtime.')
 write(OUT/'COMMITMENT_AUDIT.json',report)
 print(json.dumps(report,indent=2))
 assert not errors, errors


if __name__=='__main__':main()
