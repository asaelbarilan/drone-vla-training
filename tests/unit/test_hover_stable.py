"""D-110 regressions: noisy translation heading, fixed line and live dwell clock."""

import math

import numpy as np
import pytest

from tests.unit.test_onfly import MISSION, context
from tests.unit.test_onfly_hover import fixture
from uavlab.contracts import ProgressLabel, ProgressState, Vec3
from uavlab.plugins.control.mock import MockVelocityController


def test_heading_holds_through_residual_sign_changes_and_resumes_for_new_move():
    ctx = context()
    ctx.observation = ctx.observation.model_copy(update={"yaw_rad": 0.0})
    c = MockVelocityController(yaw_hold_radius_m=0.25)
    c.reset(MISSION, 1062)
    c._yaw_rate_toward(Vec3(x=1, y=0, z=0), ctx)
    for x, y in [(1e-5, 0), (-1e-5, 1e-5), (0, -1e-5), (0, 0)]:
        assert c._yaw_rate_toward(Vec3(x=x, y=y, z=0), ctx) == 0
    assert c._yaw_rate_toward(Vec3(x=0, y=1, z=0), ctx) > 0
    c.reset(MISSION, 1062)
    assert c._yaw_rate_toward(Vec3(x=0, y=0, z=0), ctx) == 0
    legacy = MockVelocityController()
    assert legacy._yaw_rate_toward(Vec3(x=-1e-5, y=1e-5, z=0), ctx) > 0


def test_body_pixel_does_not_move_fixed_approach_line_but_drone_drift_fails():
    obs, m = fixture()
    m._tracked_target += np.array([0, 0.38, 0])
    assert not m._hover_geometry(obs)
    m.stable_hover_reference = True
    assert m._hover_geometry(obs)
    assert not m._hover_geometry(obs.model_copy(update={"position": Vec3(x=11, y=0.4, z=3)}))
    assert not m._hover_geometry(obs.model_copy(update={"position": Vec3(x=11, y=0, z=2.6)}))


def test_dwell_does_not_count_interval_entering_window_and_rejects_source_time():
    obs, m = fixture()
    m.stable_hover_reference = True
    bad = obs.model_copy(update={"velocity": Vec3(x=1, y=0, z=0)})
    m.observe_task_evidence(bad, {})
    for i in range(1, 41):
        now = obs.model_copy(update={"t_sim_ns": i * 50_000_000, "seq": i + 1})
        m.observe_task_evidence(now, {})
    assert m._hover_s == pytest.approx(1.95)
    assert not m.stop_still_supported(now)
    now = obs.model_copy(update={"t_sim_ns": 2_050_000_000, "seq": 42})
    m.observe_task_evidence(now, {})
    assert m.stop_still_supported(now)
    assert not m.stop_still_supported(obs)
    result = ProgressState(
        label=ProgressLabel.CONTINUE,
        observation_seq=1,
        t_sim_ns=0,
        confidence=1,
        evidence="saved source",
    )
    live = m._live_hover_result(result)
    assert live.label is ProgressLabel.STOP
    assert live.t_sim_ns == now.t_sim_ns
    # A latest invalid state must also demote an old STOP.
    m.observe_task_evidence(
        now.model_copy(update={"t_sim_ns": 2_100_000_000, "yaw_rad": math.pi}), {}
    )
    assert m._live_hover_result(live).label is ProgressLabel.CONTINUE


@pytest.mark.parametrize(
    "failure", ["occluded", "no_depth", "unconfirmed", "expired", "jump", "wrong_side"]
)
def test_stable_variant_keeps_evidence_negatives(failure):
    obs, m = fixture()
    m.stable_hover_reference = True
    for i in range(41):
        now = obs.model_copy(update={"t_sim_ns": i * 50_000_000})
        m.observe_task_evidence(now, {})
    assert m.stop_still_supported(now)
    if failure == "occluded":
        from uavlab.core.frame_store import global_store

        d = global_store().get(obs.depth.uri)
        global_store().put(obs.depth.uri, np.full_like(d, 0.3))
    elif failure == "no_depth":
        now = now.model_copy(update={"depth": None})
    elif failure == "unconfirmed":
        m._tracked_confirmations = 1
    elif failure == "expired":
        m._tracked_target_t_ns = -3_000_000_000
    elif failure == "jump":
        m._tracked_target += np.array([0, 0.3, 0])
    else:
        now = now.model_copy(update={"position": Vec3(x=13, y=0, z=3)})
    assert not m.stop_still_supported(now)
