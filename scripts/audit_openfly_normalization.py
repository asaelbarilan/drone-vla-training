"""CPU-only re-decode of fixed tokens; this is not another model evaluation."""

import json
from pathlib import Path

import numpy as np

from uavlab.training.openfly_eval import native_class, score

config = json.loads(Path("D:/drone_vla_pilot/models/openfly-agent-7b/config.json").read_text())
probe = json.loads(
    Path("D:/drone_vla_pilot/runs/openfly_official_eval_20260917/probe.json").read_text()
)
rows = [
    json.loads(line)
    for line in Path("D:/drone_vla_pilot/data/openfly_eval_20260917/eval.jsonl")
    .read_text()
    .splitlines()
]
bins = np.linspace(-1, 1, config["n_action_bins"])
centers = (bins[:-1] + bins[1:]) / 2
vocab = config["text_config"]["vocab_size"] - config["pad_to_multiple_of"]
outputs = {p["decision_id"]: p for p in probe["outputs"]}
results = {}
for key in ("vln_norm", "vlnv1"):
    stats = config["norm_stats"][key]["action"]
    high, low = np.array(stats["q99"]), np.array(stats["q01"])
    decoded = []
    for row in rows:
        p = outputs[row["id"]]
        normalized = centers[
            np.clip(vocab - np.array(p["action_token_ids"]) - 1, 0, len(centers) - 1)
        ]
        action = np.where(stats["mask"], 0.5 * (normalized + 1) * (high - low) + low, normalized)
        if key == probe["norm_key"]:
            assert np.allclose(action, p["raw_action"], atol=1e-12, rtol=0)
        decoded.append(
            dict(id=row["id"], raw=action.tolist(), rounded=action.round().astype(int).tolist())
        )
    results[key] = dict(
        score=score(rows, [native_class(p["rounded"]) for p in decoded]),
        q99=stats["q99"],
        decoded=decoded,
    )
out = dict(
    kind="Post-hoc CPU normalization sensitivity, identical saved model tokens",
    original_decode_reproduced=True,
    results=results,
    limits=(
        "No new inference or prompt/history change. "
        "Does not reproduce released evaluator or flight benchmark. Original table unchanged."
    ),
)
Path("reports/vla_openfly_train_20260917/normalization_audit.json").write_text(
    json.dumps(out, indent=2)
)
print(json.dumps({key: r["score"]["all"] for key, r in results.items()}))
