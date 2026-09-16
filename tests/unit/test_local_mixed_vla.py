"""Guard against inflated action scores and hidden invalid-output failures."""

import importlib.util
from pathlib import Path

from uavlab.analysis.flight_debugger import build_decisions


def metric_module():
    spec = importlib.util.spec_from_file_location(
        "mixed_training", Path("scripts/run_local_mixed_vla.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_direction_score_rejects_translation_and_invalid_json():
    target = dict(forward_bin=32, right_bin=32, down_bin=32, yaw_cw_bin=48, stop=False)
    wrong = {**target, "forward_bin": 40}
    rows = [
        dict(task_group="visual", parsed=wrong, target=target, valid=True, exact=False),
        dict(task_group="visual", parsed=None, target=target, valid=False, exact=False),
    ]
    result = metric_module().metrics(rows)["visual"]
    assert result["correct_yaw_sign"] == 1
    assert result["correct_yaw_without_translation_or_stop"] == 0
    assert result["valid"] == 1 and result["velocity_mae_mps"] > 5
    assert result["yaw_mae_rps"] == 1.5


def test_rejected_raw_output_remains_visible_without_executed_action():
    raw = "The mission is not physical landing."
    event = dict(
        event_type="decision_proposed",
        t_sim_ns=0,
        seq=0,
        trace_id="invalid-0",
        payload=dict(
            producer="actual_smol256",
            kind="invalid_model_output",
            rejected=True,
            source_observation_seq=1,
            source_t_sim_ns=0,
            raw_response=raw,
            diagnostic_only=True,
        ),
    )
    recording = dict(role="policy", observation_seq=1, completed_t_sim_ns=0, response=raw)
    (decision,) = build_decisions([event], [dict(observation_seq=1, t=0)], [recording])
    assert decision["state"] == "rejected"
    assert decision["recording"]["response"] == raw
    assert decision["control_count"] == 0
