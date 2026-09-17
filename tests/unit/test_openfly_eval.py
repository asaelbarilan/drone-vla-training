from uavlab.training.openfly_eval import frd_class, native_class, score


def test_native_does_not_silently_turn_unknown_into_stop():
    assert native_class([0] * 8) == "hold"
    assert native_class([1, 3, 0, 0, 0, 0, 0, 0]) == "mixed"
    assert native_class([0, 5, 0, 0, 0, 0, 0, 0]) == "forward"
    assert native_class([0, 0, 15, 0, 0, 0, 0, 0]) == "left_turn"
    assert native_class([2, 0, 0, 0, 0, 0, 0, 0]) == "invalid"


def test_frd_signs_and_stop_false_positives():
    r = dict(forward_bin=32, right_bin=32, down_bin=32, yaw_cw_bin=31, stop=False)
    assert frd_class(r) == "left_turn"
    r["yaw_cw_bin"] = 32
    r["down_bin"] = 31
    assert frd_class(r) == "up"
    rows = [dict(split="seen", target_class="forward"), dict(split="unseen", target_class="stop")]
    result = score(rows, ["stop", "stop"])
    assert result["all"]["correct"] == 1
    assert result["all"]["false_stop"] == 1
    assert result["all"]["macro_recall"] == 0.5
