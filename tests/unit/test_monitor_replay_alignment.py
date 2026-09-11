"""A delayed monitor answer must be scored at image capture, not activation."""

import importlib

import pytest


@pytest.mark.parametrize("module", ["scripts.analyze_onfly_run", "scripts.analyze_onfly_yaw"])
def test_visibility_change_during_inference_does_not_change_grounding_score(module):
    index = importlib.import_module(module)._monitor_source_index
    reply = {"t_sim_ns": 5_000_000_000, "payload": {"evidence_observation_seq": 20}}
    frames = {20: True, 100: False}
    grouped = index([reply])
    assert list(grouped) == [20]
    assert frames[next(iter(grouped))] is True
    assert index([{"t_sim_ns": 5_000_000_000, "payload": {}}]) == {}
