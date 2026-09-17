"""Audit D137 executed schedules and summarize frozen generation probes."""

import argparse
import json
import math
from pathlib import Path

from run_local_mixed_vla import metrics
from summarize_local_mixed import summarize

p = argparse.ArgumentParser()
p.add_argument("--reports", type=Path, required=True)
a = p.parse_args()
for model in ("smol256", "smol500"):
    path = a.reports / f"{model}_duration_report.json"
    if not path.exists():
        continue
    r = json.loads(path.read_text())
    assert r["status"] == "complete" and r["updates"] == 1200
    ls = json.loads((a.reports / f"{model}_duration_losses.json").read_text())
    assert [x["step"] for x in ls] == list(range(r["start_step"] + 1, 1201))
    assert [x["sample_id"] for x in ls] == r["training_schedule"][r["start_step"] :]
    assert set(r["training_schedule"]) == set(r["train_ids"])
    assert not set(r["train_ids"]) & set(r["val_ids"])
    assert all(
        math.isfinite(x["loss"]) and math.isfinite(x["gradient_norm"]) and x["gradient_norm"] > 0
        for x in ls
    )
    assert r["reload_spot_identical"]
    r["validation_loss"] = [
        dict(
            step=x["step"],
            mean_answer_ce=next(
                v["answer_ce"]
                for v in x["measurements"]
                if v["split"] == "val" and v["group"] == "all"
            ),
        )
        for x in r["comparable_losses"]
    ]
    out = summarize(r, expected_updates=1200)
    out["at400"] = metrics(r["generation_checkpoints"]["400"])
    out["schedule_audit"] = dict(
        updates_executed=len(ls),
        start_step=r["start_step"],
        schedule_identical=True,
        disjoint_splits=True,
    )
    out["stop_exact_at400"] = sum(
        x["exact"] for x in r["generation_checkpoints"]["400"] if x["target"]["stop"]
    )
    out["stop_exact_at1200"] = sum(x["exact"] for x in r["after"] if x["target"]["stop"])
    (a.reports / f"{model}_summary.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
