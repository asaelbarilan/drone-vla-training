"""Check comparable masked weighted loss and preserve the original schedule prefix."""

import importlib.util
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("duration", ROOT / "scripts/run_smol_duration.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_action_loss_uses_shift_mask_and_value_weights():
    logits = torch.tensor([[[8.0, 0.0], [0.0, 0.0], [0.0, 2.0], [9.0, 0.0]]])
    batch = {
        "labels": torch.tensor([[-100, -100, 1, 0]]),
        "loss_weights": torch.tensor([[0.0, 0.0, 0.25, 0.75]]),
    }
    expected = 0.25 * torch.log(torch.tensor(2.0)) + 0.75 * torch.log1p(
        torch.exp(torch.tensor(2.0))
    )
    assert torch.allclose(m.action_loss(logits, batch), expected)
    logits[0, 0] = torch.tensor([-100.0, 100.0])
    logits[0, 3] = torch.tensor([-100.0, 100.0])
    assert torch.allclose(m.action_loss(logits, batch), expected)


def test_extended_order_preserves_original_prefix_and_only_train_ids():
    manifest = json.loads(
        (ROOT / "reports/vla_smol_mixed_20260917/mixed_manifest.json").read_text()
    )
    prior = json.loads(
        (ROOT / "reports/vla_smol_mixed_20260917/smol256_mixed_report.json").read_text()
    )
    rows = [{"decision_id": k} for k in prior["train_ids"]]
    order = m.extended_schedule(rows, manifest["training_schedule"])
    assert len(order) == 1200
    assert order[:400] == manifest["training_schedule"]
    assert set(order) == set(prior["train_ids"])
    assert not set(order) & set(prior["val_ids"])
    for start in range(0, 1008, 252):
        assert len(set(order[start : start + 252])) == 252
