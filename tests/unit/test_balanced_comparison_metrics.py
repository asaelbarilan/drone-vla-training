"""Synthetic scorer regression: perfect targets, directional collapse and STOP spam."""

import importlib
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
metrics = importlib.import_module("run_smol_duration").metrics


def prediction(target, parsed):
    return dict(
        target=target,
        parsed=parsed,
        valid=parsed is not None,
        task_group="visual",
        exact=parsed == target,
    )


def test_visual_direction_rejects_stop_translation_and_invalid():
    right = dict(forward_bin=32, right_bin=32, down_bin=32, yaw_cw_bin=40, stop=False)
    left = {**right, "yaw_cw_bin": 24}
    targets = [left, right] * 8
    correct = [prediction(t, t) for t in targets]
    assert metrics(correct)["visual"]["correct_yaw_without_translation_or_stop"] == 16
    collapsed = [prediction(t, right) for t in targets]
    assert metrics(collapsed)["visual"]["correct_yaw_without_translation_or_stop"] == 8
    for bad in (None, {**right, "stop": True}, {**right, "forward_bin": 35}):
        assert (
            metrics([prediction(t, bad) for t in targets])["visual"][
                "correct_yaw_without_translation_or_stop"
            ]
            == 0
        )
