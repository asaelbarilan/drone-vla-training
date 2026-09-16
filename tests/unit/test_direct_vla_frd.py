import json
import math
import random

import pytest

from uavlab.contracts import ControlCommand, Vec3
from uavlab.training import direct_vla_contract as flu
from uavlab.training import direct_vla_frd as frd


@pytest.mark.parametrize(
    "bins,expected,yaw_rate",
    [
        ((40, 32, 32, 32), (1.25, 0, 0), 0),
        ((32, 40, 32, 32), (0, -1.25, 0), 0),
        ((32, 32, 40, 32), (0, 0, -1.25), 0),
        ((32, 32, 32, 40), (0, 0, 0), -0.375),
    ],
)
def test_cardinal_signs(bins, expected, yaw_rate):
    action = frd.action_from_target(frd.FRDTarget(*bins), 0, duration_s=0.2)
    assert action.velocity.as_tuple() == pytest.approx(expected)
    assert action.yaw_rate_rps == pytest.approx(yaw_rate)


def test_heading_not_world_or_tilted_body():
    action = frd.action_from_target(frd.FRDTarget(40, 40, 40, 32), math.pi / 2, duration_s=0.2)
    assert action.velocity.as_tuple() == pytest.approx((1.25, 1.25, -1.25))


def test_random_physical_equivalence():
    rng = random.Random(131)
    for _ in range(4096):
        command = ControlCommand(
            t_sim_ns=0,
            velocity=Vec3(x=rng.uniform(-2, 2), y=rng.uniform(-2, 2), z=rng.uniform(-2, 2)),
            yaw_rate_rps=rng.uniform(-1.5, 1.5),
        )
        yaw = rng.uniform(-math.pi, math.pi)
        old = flu.target_from_command(command, yaw)
        new = frd.target_from_command(command, yaw)
        assert frd.to_flu(new) == old
        assert frd.parse_target(frd.target_json(new)) == new
        assert frd.action_from_target(new, yaw, duration_s=0.2) == flu.action_from_target(
            old, yaw, duration_s=0.2
        )


def test_contracts_cannot_silently_mix():
    old = flu.DirectVLATarget(32, 32, 32, 32)
    new = frd.FRDTarget(32, 32, 32, 32)
    with pytest.raises(ValueError):
        frd.parse_target(flu.target_json(old))
    with pytest.raises(ValueError):
        flu.parse_target(frd.target_json(new))
    with pytest.raises(TypeError):
        frd.action_from_target(old, 0, duration_s=0.2)
    assert frd.action_from_target(new, 0, duration_s=0.2) is not None
    assert frd.action_from_target(frd.FRDTarget(32, 32, 32, 32, True), 0, duration_s=0.2) is None


@pytest.mark.parametrize(
    "field,value", [("right_bin", True), ("down_bin", 65), ("stop", 1), ("yaw_cw_bin", -1)]
)
def test_invalid_fields_rejected(field, value):
    payload = json.loads(frd.target_json(frd.FRDTarget(32, 32, 32, 32)))
    payload[field] = value
    with pytest.raises(ValueError):
        frd.parse_target(json.dumps(payload))


def test_duplicate_and_moving_stop_rejected():
    with pytest.raises(ValueError):
        frd.parse_target(
            '{"forward_bin":32,"forward_bin":40,"right_bin":32,"down_bin":32,"yaw_cw_bin":32,"stop":false}'
        )
    with pytest.raises(ValueError):
        frd.FRDTarget(40, 32, 32, 32, True)
