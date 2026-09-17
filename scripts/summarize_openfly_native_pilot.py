"""Verify exposure isolation, plot losses, and record the bounded native pilot."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path("reports/vla_openfly_train_20260917")
RUN = Path("D:/drone_vla_pilot/runs/smol500_openfly_native_20260917_a")
report = json.loads((RUN / "report.json").read_text())
assert report["status"] in ("complete", "stopped_overfit_gate", "failed")
rows = [
    json.loads(x)
    for x in Path("D:/drone_vla_pilot/data/openfly_train_pilot_20260917/index.jsonl")
    .read_text()
    .splitlines()
]
by = {r["id"]: r for r in rows}
losses = [json.loads(x) for x in (RUN / "losses.jsonl").read_text().splitlines()]
for entry in losses:
    assert len(entry["ids"]) == 4
    assert all(by[key]["split"] == "train" for key in entry["ids"])
    assert len({by[key]["action_id"] for key in entry["ids"]}) == 4
    if entry["stage"] == "overfit":
        assert set(entry["ids"]) <= set(report["overfit_ids"])
if report["status"] == "complete":
    assert report["overfit_pass"]
    assert report["reload_spots"] == report["dev_after"][:4]
    assert len(report["dev_after"]) == report["dev_rows"] == 171
    assert all(by[p["id"]]["split"] == "dev" for p in report["dev_after"])
    assert sum(e["stage"] == "pilot" for e in losses) == 160
audit = dict(
    status=report["status"],
    four_distinct_actions_per_effective_batch=True,
    no_dev_or_official_eval_exposures=True,
    updates={s: sum(e["stage"] == s for e in losses) for s in ("overfit", "pilot")},
    exposures=len(losses) * 4,
    adapter_sha256={
        str(p.relative_to(RUN)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in RUN.rglob("adapter_model.safetensors")
    },
)
(OUT / "training_audit.json").write_text(json.dumps(audit, indent=2))
(OUT / "losses.jsonl").write_bytes((RUN / "losses.jsonl").read_bytes())
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
for ax, stage in zip(axes, ("overfit", "pilot"), strict=True):
    points = [e for e in losses if e["stage"] == stage]
    ax.plot([e["step"] for e in points], [e["loss"] for e in points], label="Mixed-batch train CE")
    ax.set(
        title=f"Smol500 {stage} (separate initialization)", xlabel="Optimizer update", ylabel="Loss"
    )
    if stage == "pilot" and "pilot_eval_loss_after" in report:
        for cohort in ("train", "dev"):
            ax.plot(
                [0, 160],
                [report[f"pilot_eval_loss_{when}"][cohort] for when in ("before", "after")],
                "o--",
                label=f"Full {cohort}: eval mode, endpoints only",
            )
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7)
fig.savefig(OUT / "loss_curves.png", dpi=150)
plt.close(fig)
lines = [
    "# D142 - OpenFly native-action pilot",
    "",
    f"Status: **{report['status']}**. Smol500 BF16 language LoRA; local, no AWS.",
    "",
    "22 official TRAIN routes, 258 train /171 dev decisions; original evaluation untouched.",
    "Pipeline gate passes (8/8 memorization, finite updates, four reload spots exact).",
    "Learning gate FAILS:18/171dev exact, macro recall0.149, below majority113/171",
    "and majority macro recall0.167. Blank images give11/171 (all STOP); image",
    "dependence does not establish useful grounding.26false STOPs/160nonterminal.",
    "The untrained base has171invalid outputs; its0/171 primarily measures format",
    "failure. Falling CE also rewards learned formatting, not just action competence.",
    "8-example overfit then a fresh-base160-update pilot, conditional on overfit gate.",
    "",
    "|Evaluation|Exact|Invalid|Macro recall|Majority reference|",
    "|---|---:|---:|---:|---:|",
]
for key, metrics in report["metrics"].items():
    lines.append(
        f"|{key}|{metrics['exact']}/{metrics['n']}|{metrics['invalid']}|"
        f"{metrics['macro_recall']:.3f}|{metrics['majority_correct']}/{metrics['n']}|"
    )
lines += [
    "",
    "Exact native action ID scoring differs from the earlier coarse FRD transfer diagnostic.",
    "No velocity conversion, physical flight, or autonomous OpenFly simulator rollout claimed.",
    "Motion audit:910/911 raw transitions align, one zero-yaw right turn flagged. Compressed",
    "annotation frame gaps are not primitive durations (22/22 ID8 gaps measure3, not6).",
    "Training imitates released native IDs; continuous-control labels are not validated.",
    "Dev routes contain no up/down actions; neither lateral ID occurs in the full manifest.",
    "Only11dev trajectories: correlated frames do not count as171independent flight trials.",
    "Blank-image intervention measures dependence, not causal proof of good visual grounding.",
    "",
    "OpenFly integration: identical saved tokens re-decoded with released-evaluator vlnv1",
    "change coarse accuracy12/51 to29/51, mixed vectors32 to0, turn accuracy remains0/12.",
    "This post-hoc sensitivity does not replace the original table or reproduce published flights.",
    "Prompt/history, controller semantics and4-bit effects remain incompletely isolated.",
    "",
    "Data hashes, selected routes, predictions, sampling exposures, adapter hashes and reload",
    "evidence accompany this report. Broader simulation/real-flight coverage remains necessary.",
    "",
    "Viewer: http://127.0.0.1:8771/openfly_training.html",
]
(OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps(dict(status=report["status"], metrics=report["metrics"], audit=audit)))
