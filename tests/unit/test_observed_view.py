"""Observed-view option contracts. Model stubs never navigate by simulator truth."""
import asyncio
import math

import pytest

from tests.unit.test_onfly import MISSION, StubModel, context, services
from tests.unit.test_router import make_router
from uavlab.contracts import ProgressLabel, ProgressState, Vec3, s_to_ns
from uavlab.core.clock import SimClock
from uavlab.core.config import Authority
from uavlab.core.services import bind
from uavlab.interfaces import RoutingFeedback
from uavlab.plugins.reasoning.observed_view import ObservedViewPolicy, ObservedViewVerifier

TARGET = '{"evidence":"red tower","kind":"target","u":500,"v":500}'
POINT = '{"evidence":"open ground","kind":"exploration","u":700,"v":500}'
BACK = '{"evidence":"target absent now","action":"backtrack"}'


def setup(replies=None):
    model = StubModel(replies or [TARGET, BACK, POINT])
    policy = ObservedViewPolicy(grounded_waypoints=True,
                                coordinate_contract='qwen_relative_1000')
    policy.reset(MISSION, 1061)
    bind(policy, services(model))
    ctx = context()
    ctx.observation = ctx.observation.model_copy(update={
        'range_rays':tuple([25.0]*len(ctx.observation.ray_bearings_rad))})
    return policy, model, ctx


def move(policy, ctx, t, x=None, yaw=None):
    changes = dict(t_sim_ns=s_to_ns(t), seq=int(t*20)+1)
    if x is not None:
        changes['position'] = Vec3(x=x, y=0, z=3)
    if yaw is not None:
        changes['yaw_rad'] = yaw
    ctx.observation = ctx.observation.model_copy(update=changes)
    ctx.t_sim_ns = s_to_ns(t)
    policy.services.clock = SimClock(start_ns=ctx.t_sim_ns)


def lost(ctx):
    ctx.last_progress = ProgressState(label=ProgressLabel.LOST,
        observation_seq=ctx.observation.seq,t_sim_ns=ctx.t_sim_ns)


def selected():
    policy, model, ctx = setup()
    asyncio.run(policy.decide(ctx))
    move(policy,ctx,1,x=2,yaw=-1)
    lost(ctx)
    result = asyncio.run(policy.decide(ctx))
    return policy,model,ctx,result


def test_model_choice_binds_stored_pose_heading_and_no_terminal_stop():
    policy,model,ctx,result = selected()
    assert len(model.requests)==2
    assert model.requests[-1].image_count==2
    assert result.payload.target==policy.anchor.position
    assert result.payload.view_yaw_rad==policy.anchor.yaw
    assert not result.payload.stop_at_target
    verifier=ObservedViewVerifier()
    verifier.reset(MISSION,1061)
    assert verifier.verify(result,ctx).accepted
    forged=result.model_copy(update={'payload':result.payload.model_copy(
        update={'target':Vec3(x=50,y=0,z=3)})})
    assert not verifier.verify(forged,ctx).accepted


def test_normal_lost_without_anchor_uses_current_image_no_return_request():
    policy,model,ctx=setup([POINT])
    lost(ctx)
    asyncio.run(policy.decide(ctx))
    assert model.requests[0].image_count==1
    assert policy.return_requests==0


def test_old_anchor_is_not_offered():
    policy,model,ctx=setup([TARGET,POINT])
    asyncio.run(policy.decide(ctx))
    move(policy,ctx,31,x=2)
    lost(ctx)
    asyncio.run(policy.decide(ctx))
    assert policy.return_requests==0
    assert model.requests[-1].image_count==1


def test_completion_requires_heading_and_next_fresh_view_no_second_return():
    policy,model,ctx,_=selected()
    move(policy,ctx,2,x=0,yaw=policy.anchor.yaw+1)
    assert asyncio.run(policy.decide(ctx)).provenance['observed_view_phase']=='returning'
    move(policy,ctx,3,x=0,yaw=policy.anchor.yaw)
    completed=asyncio.run(policy.decide(ctx))
    assert completed.provenance['observed_view_phase']=='view_restored'
    assert len(model.requests)==2
    move(policy,ctx,4)
    asyncio.run(policy.decide(ctx))
    assert len(model.requests)==3 and model.requests[-1].image_count==1
    assert policy.return_requests==1


@pytest.mark.parametrize('reason',['timeout','blocked'])
def test_return_is_bounded_and_does_not_retry(reason):
    policy,model,ctx,result=selected()
    if reason=='timeout':
        move(policy,ctx,22,x=2)
    else:
        ctx.last_routing_feedback=RoutingFeedback(result.decision_id,False,
            'planner reported infeasible',result.kind,None,ctx.t_sim_ns)
        move(policy,ctx,2,x=2)
    ended=asyncio.run(policy.decide(ctx))
    assert ended.provenance['return_outcome']==('expired' if reason=='timeout' else 'blocked')
    assert ended.payload.target==ctx.observation.position
    assert policy.active is None
    assert policy.return_requests==1 and len(model.requests)==2


def test_bound_option_still_rejected_when_obstacle_blocks_endpoint():
    policy,model,ctx,result=selected()
    distance=ctx.observation.position.distance_to(result.payload.target)
    ctx.observation=ctx.observation.model_copy(update={'range_rays':tuple([distance]*len(ctx.observation.ray_bearings_rad))})
    verifier=ObservedViewVerifier()
    verifier.reset(MISSION,1061)
    assert not verifier.verify(result,ctx).accepted


def test_router_controller_restore_view_heading_at_position():
    policy,model,ctx,result=selected()
    router=make_router(Authority.WAYPOINT)
    router.verifier=ObservedViewVerifier()
    router.verifier.reset(MISSION,1061)
    assert router.accept(result,ctx).accepted
    move(policy,ctx,1.1,x=0,yaw=policy.anchor.yaw-0.5)
    command,_,_=router.command_for_tick(ctx)
    assert command.velocity.norm()<1e-8
    assert command.yaw_rate_rps>0
    move(policy,ctx,1.2,x=0,yaw=policy.anchor.yaw)
    command,_,_=router.command_for_tick(ctx)
    assert abs(command.yaw_rate_rps)<1e-8
    assert not router.stop_requested


@pytest.mark.parametrize('yaw',[math.inf,math.nan])
def test_nonfinite_view_heading_is_rejected(yaw):
    from pydantic import ValidationError

    from uavlab.contracts import WaypointGoal
    with pytest.raises(ValidationError):
        WaypointGoal(target=Vec3(x=0,y=0,z=3),view_yaw_rad=yaw)


def test_stationary_view_goal_uses_shared_super_hold_with_braking_check():
    from tests.unit.test_super_planner import context, observation
    from uavlab.contracts import WaypointGoal
    from uavlab.plugins.planning.super import SuperLocalPlanner

    planner = SuperLocalPlanner()
    planner.reset(MISSION, 1061)
    ctx = context(observation())
    goal = WaypointGoal(target=ctx.observation.position, view_yaw_rad=1.0)
    result = planner.plan(goal, ctx)
    assert result.feasible and result.reason == "verified observation hold"
    assert result.points[-1].velocity.norm() == 0
    planner.reset(MISSION, 1061)
    blocked = context(observation(ranges=tuple([0.1]*24)))
    assert not planner.plan(goal, blocked).feasible
