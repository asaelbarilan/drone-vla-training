"""Saved-state SUPER/controller fixture; stub choice, no inference and no benchmark claim."""
import asyncio
import json
from pathlib import Path

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import (
    ControlCommand,
    MemorySnapshot,
    MissionSpec,
    PerceptionState,
    ProgressLabel,
    ProgressState,
    Vec3,
    WaypointGoal,
)
from uavlab.core.clock import SimClock
from uavlab.core.compose import load_architecture
from uavlab.core.decision_router import DecisionRouter
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.frame_store import global_store
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult, RoutingFeedback
from uavlab.plugins.reasoning.observed_view import ObservedView

OUT=Path('reports/recovery_cycle_20260915/return_component')
ROOT=Path('runs/c5_clutter_qwen4_20260915_s1061')


class Choice:
    async def invoke(self, request):
        return InferenceResult(payload='{"action":"backtrack","evidence":"fixture choice"}',
                               output_tokens=8,latency_ns=0)


def context(obs,mission,scratch):
    return DecisionContext(mission=mission,observation=obs,
        perception=PerceptionState(observation_seq=obs.seq,t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq,t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,t_wall_ns=0,episode_id='return-component',scratch=scratch)


async def main():
    OUT.mkdir(exist_ok=True)
    m=json.loads((ROOT/'manifest.json').read_text())
    cfg=m['environment_config']
    mission=MissionSpec(mission_id='return-component',instruction=cfg['instruction'],
        task_family=cfg['task_family'],success=cfg['params']['success'],
        constraints=cfg['params']['constraints'])
    arch=load_architecture('c5_observed_view_return_qwen4_dev')
    env=DeterministicEnv(**cfg['params'])
    await env.reset(mission,1061)
    components={role:REGISTRY.build(role,getattr(arch,role).name,getattr(arch,role).params)
                for role in ['policy','planner','verifier','controller']}
    for component in components.values():
        component.reset(mission,1061)
    policy=components['policy']
    services=RuntimeServices(SimClock(),EventLog('return-component',None),FeatureCache(),Choice())
    bind(policy,services)
    router=DecisionRouter(arch,planner=components['planner'],verifier=components['verifier'],
                          controller=components['controller'],shield=None)
    router.reset(mission,1061)
    scratch={}
    events=[json.loads(x) for x in (ROOT/'events.jsonl').read_text().splitlines()]
    controls=[e for e in events if e['event_type']=='control' and e['t_sim_ns']<39_200_000_000]
    goals={e['t_sim_ns']:WaypointGoal.model_validate(e['payload']['decision_payload'])
           for e in events if e['event_type']=='decision_proposed'
           and 'decision_payload' in e['payload'] and e['t_sim_ns']<39_200_000_000}
    for e in controls:
        obs=await env.observe()
        p=e['payload']
        assert obs.position.distance_to(Vec3(x=p['position_x'],y=p['position_y'],
                                            z=p['position_z']))<1e-7
        if obs.seq==680:
            policy.anchor=ObservedView(obs.position,obs.yaw_rad,obs.seq,obs.t_sim_ns,
                                      global_store().get(obs.rgb.uri).copy())
            policy.anchor.image.save(OUT/'anchor.png')
        if obs.t_sim_ns in goals:
            components['planner'].plan(goals[obs.t_sim_ns],context(obs,mission,scratch))
        await env.step(ControlCommand(t_sim_ns=obs.t_sim_ns,
            velocity=Vec3(x=p['vx'],y=p['vy'],z=p['vz']),yaw_rate_rps=p['yaw_rate']),50_000_000)
    rows=[]
    decisions=[]
    feedback=None
    for tick in range(501):
        obs=await env.observe()
        ctx=context(obs,mission,scratch)
        ctx.last_progress=ProgressState(label=ProgressLabel.LOST,observation_seq=obs.seq,
                                        t_sim_ns=obs.t_sim_ns)
        ctx.last_routing_feedback=feedback
        if tick%20==0:
            services.clock=SimClock(start_ns=obs.t_sim_ns)
            proposal=await policy.decide(ctx)
            routed=router.accept(proposal,ctx)
            feedback=RoutingFeedback(proposal.decision_id,routed.accepted,routed.reason,
                                     proposal.kind,None,obs.t_sim_ns)
            decisions.append(dict(t=obs.t_sim_ns/1e9,phase=proposal.provenance.get(
                'observed_view_phase'),accepted=routed.accepted,reason=routed.reason,
                plan_reason=routed.trajectory.reason if routed.trajectory else None))
            global_store().get(obs.rgb.uri).save(OUT/f'view_{tick}.png')
            if policy.return_outcome in ['view_restored','blocked','expired']:
                break
        command,_,_=router.command_for_tick(ctx)
        rows.append(dict(t=obs.t_sim_ns/1e9,position=obs.position.model_dump(),yaw=obs.yaw_rad,
                          velocity=command.velocity.model_dump(),yaw_rate=command.yaw_rate_rps))
        await env.step(command,50_000_000)
        if env.status().collided:
            raise AssertionError('Return fixture collision')
    result=dict(type='saved-state component with stub semantic choice, not a model flight',
        prefix_poses=len(controls),outcome=policy.return_outcome,
        final_position=obs.position.model_dump(),final_yaw=obs.yaw_rad,
        anchor_position=policy.anchor.position.model_dump(),anchor_yaw=policy.anchor.yaw,
        position_error=obs.position.distance_to(policy.anchor.position),
        collision_count=env.status().collision_count,decisions=decisions,controls=rows)
    (OUT/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='controls'},indent=2))


if __name__=='__main__':
    asyncio.run(main())
