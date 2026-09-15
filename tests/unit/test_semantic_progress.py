"""Visibility is evidence; opt-in semantic progress is an independent judgment."""
import asyncio
import json

import pytest

from tests.unit.test_onfly import MISSION, StubModel, context, services
from tests.unit.test_onfly_target_stop import fresh, setup_monitor
from uavlab.contracts import ProgressLabel
from uavlab.core.services import bind
from uavlab.plugins.reasoning.onfly import OnFlyMonitor


@pytest.mark.parametrize('semantic',[False,True])
def test_absent_continue_is_not_rewritten_in_semantic_variant(semantic):
    answer=dict(evidence='target occluded behind structure',visible=False,u=None,v=None)
    if semantic:
        answer['status']='CONTINUE'
    model=StubModel([json.dumps(answer)])
    monitor=OnFlyMonitor(current_grounding=True,structured_evidence=True,
                         target_bound_stop=True,semantic_progress=semantic,
                         layout="history_sheet_plus_latest")
    bind(monitor,services(model))
    monitor.reset(MISSION,1061)
    monitor._ever_acquired=True
    result=asyncio.run(monitor.assess(context()))
    assert result.label is (ProgressLabel.CONTINUE if semantic else ProgressLabel.LOST)
    assert not result.recovery_anchor_valid
    assert not result.recovery_reacquired
    assert ('chronological HISTORY' in model.requests[0].prompt) is semantic


@pytest.mark.parametrize('status',['LOST','STOP'])
def test_absent_semantic_verdict_cannot_stop(status):
    ctx,monitor,model=setup_monitor()
    monitor.current_grounding=monitor.semantic_progress=True
    monitor._ever_acquired=True
    model.replies=[json.dumps(dict(evidence='no red target',visible=False,u=None,v=None,
                                  status=status))]
    assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.LOST


@pytest.mark.parametrize('depth,expected',[(1.0,ProgressLabel.STOP),(20.0,ProgressLabel.CONTINUE)])
def test_semantic_stop_retains_metric_and_distinct_frame_checks(depth,expected):
    ctx,monitor,model=setup_monitor(depth_m=depth)
    monitor.current_grounding=monitor.semantic_progress=True
    model.replies=[json.dumps(dict(evidence='red target',visible=True,u=500,v=500,status='STOP'))]
    assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE
    fresh(ctx)
    assert asyncio.run(monitor.assess(ctx)).label is expected


def test_progress_variant_requires_current_grounding():
    with pytest.raises(ValueError,match='requires current grounding'):
        OnFlyMonitor(semantic_progress=True)


def test_progress_variant_requires_separate_current_image():
    with pytest.raises(ValueError,match="requires history_sheet_plus_latest"):
        OnFlyMonitor(semantic_progress=True,current_grounding=True,layout="multi_image")
