"""Batch composition, leakage rejection and true mean-gradient equivalence."""

import pytest
import torch

from uavlab.training.mixed_batches import (
    GROUPS,
    backward_mixed_batch,
    balanced_schedule,
    task_class,
)


def rows():
    result = []
    for group in GROUPS:
        for i in range(3):
            target = dict(
                forward_bin=32, right_bin=32, down_bin=32, yaw_cw_bin=32, stop=group == "stop"
            )
            if group == "motion":
                target["forward_bin"] = 36
            if group == "visual":
                target["yaw_cw_bin"] = 40
            result.append(
                dict(
                    decision_id=f"{group}{i}",
                    split="train",
                    seed=1501 + i,
                    task_group="visual" if group == "visual" else "coordinate",
                    target=target,
                )
            )
    return result


def test_balancing_coverage_and_validation_exclusion():
    data = rows()
    val = {**data[0], "decision_id": "val", "split": "val", "seed": 1500}
    schedule = balanced_schedule([*data, val], 12)
    lookup = {r["decision_id"]: r for r in data}
    assert schedule == balanced_schedule([*data, val], 12)
    for batch in schedule:
        assert len(batch) == 4
        assert {task_class(lookup[k]) for k in batch} == set(GROUPS)
    for group in GROUPS:
        first_cycle = [k for batch in schedule[:3] for k in batch if task_class(lookup[k]) == group]
        assert len(set(first_cycle)) == 3
    with pytest.raises(ValueError):
        balanced_schedule([*data, {**val, "split": "train"}], 1)
    with pytest.raises(ValueError):
        balanced_schedule([r for r in data if task_class(r) != "stop"], 1)


def test_accumulated_gradients_equal_batch_mean():
    data = rows()
    lookup = {r["decision_id"]: r for r in data}
    batch = balanced_schedule(data, 1)[0]
    parameter = torch.tensor(2.0, requires_grad=True)
    coeff = {identity: float(i + 1) for i, identity in enumerate(batch)}
    value = backward_mixed_batch(
        batch, lookup, lambda r: (parameter - coeff[r["decision_id"]]) ** 2
    )
    reference = torch.tensor(2.0, requires_grad=True)
    expected = torch.stack([(reference - coeff[k]) ** 2 for k in batch]).mean()
    expected.backward()
    assert value == pytest.approx(expected.item())
    torch.testing.assert_close(parameter.grad, reference.grad)
    lookup[batch[0]]["split"] = "val"
    with pytest.raises(ValueError):
        backward_mixed_batch(batch, lookup, lambda r: parameter**2)
