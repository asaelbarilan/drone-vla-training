import pytest

from uavlab.training.action_value_loss import value_token_weights
from uavlab.training.direct_vla_frd import FIELDS, FRDTarget, target_json


def test_each_value_has_equal_mass_even_with_different_length():
    text = target_json(FRDTarget(1, 32, 64, 0, False))
    offsets = [(i, i + 1) for i in range(len(text))]
    weights, fields = value_token_weights(text, offsets)
    assert sum(weights) == pytest.approx(1)
    for field in (*FIELDS, "stop"):
        assert sum(w for w, f in zip(weights, fields, strict=True) if f == field) == pytest.approx(
            0.18
        )
    assert sum(w for w, f in zip(weights, fields, strict=True) if f is None) == pytest.approx(0.1)
    assert weights[-1] > 0 and fields[-1] is None


def test_reject_cross_boundary_or_missing_offsets():
    text = target_json(FRDTarget(32, 32, 32, 32, True))
    with pytest.raises(ValueError, match="crosses"):
        value_token_weights(text, [(0, len(text))])
    with pytest.raises(ValueError, match="missing"):
        value_token_weights(text, [])
    with pytest.raises(ValueError, match="canonical"):
        value_token_weights("{}", [(0, 1), (1, 2)])
