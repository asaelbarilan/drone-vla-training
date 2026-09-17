# ruff: noqa: E501
"""Write D141 final report only after complete inference and audited local flights."""

import json
import subprocess
from pathlib import Path

root = Path("reports/vla_expanded_models_20260917")
s = json.loads((root / "summary.json").read_text())
assert len(s["official_transfer"]) == 4
assert all(v["status"] == "complete" for v in s["local"].values())
lines = [
    "# D141 - Expanded-data models and official OpenFly transfer",
    "",
    "Completed local400-update Smol500 and Qwen3-VL4B runs on the frozen expanded data;Smol256 reference reused. No AWS spending or physical flights.",
    "",
    "## Local development results",
    "",
    "|Model|Original visual|New visual|STOP exact|False STOP|Pilot gate|",
    "|---|---:|---:|---:|---:|---|",
]
for model, item in s["local"].items():
    m = item["metrics"]
    b = m["boundaries"]
    false = sum(v["predicted_stop"] for k, v in b.items() if k != "stop")
    lines.append(
        f"|{model}|{m['original']['visual']['correct_yaw_without_translation_or_stop']}/16|{m['new']['visual']['correct_yaw_without_translation_or_stop']}/64|{b['stop']['exact']}/6|{false}/128|{m['combined_pilot_gate']}|"
    )
lines += [
    "",
    "Same400updates/1600exposures,balanced visual/motion/HOLD/STOP,seed132,r8,identical sample schedule. SmolBF16 vs QwenNF4;native tokenizers/processors differ. Cross-model CE magnitudes are not comparable. Four final checkpoint reload spots must match.",
    "",
    "## Official OpenFly offline transfer",
    "",
    "|Model|All|Seen|Unseen|Macro recall|False STOP|",
    "|---|---:|---:|---:|---:|---:|",
]
for model, v in s["official_transfer"].items():
    a = v["all"]
    seen = v["seen"]
    unseen = v["unseen"]
    lines.append(
        f"|{model}|{a['correct']}/{a['n']}|{seen['correct']}/{seen['n']}|{unseen['correct']}/{unseen['n']}|{a['macro_recall']:.3f}|{a['false_stop']}/{a['nonterminal']}|"
    )
lines += [
    "",
    "51decisions from14official evaluation trajectories,41seen/10unseen,selected deterministically before inference. Majority-forward reference26/51. Two unsupported negative annotationIDs excluded and logged. Exact image/pose/yaw/coarse-action alignment verified. No external rows admitted totraining.",
    "",
    "This is an offline coarse-action diagnostic on expert-recorded observations,not an official full benchmark,exact action-amplitude comparison,or closed-loop flight success. OpenFlyusesNF4,training chat template,vln_norm,two preceding frames+current. Localadapters receive currentfront only with missingdowncamera/odometry explicit. No state fabricated;no future frames,targetactions or targetposes in prompts. Multi-stage instructions and missinghistory limit transfer interpretation.",
    "",
    "## Local simulation flights",
    "",
]
for model in ("smol500", "qwen"):
    audit = json.loads((root / f"{model}_flight_audit.json").read_text())
    result = json.loads((root / f"{model}_flight_summary.json").read_text())
    assert (root / f"{model}_flight_ui/model_ui_check.json").exists()
    for r in result["results"]:
        lines.append(
            f"- {model},seed{r['seed']}: {r['termination_reason']};success={r['success']};distance={r['metrics']['distance_to_goal_m']:.3f}m."
        )
lines += [
    "",
    "Simulation pauses during inference. Actualmodeloutputs drive the controller;teacher is evaluation reference. OpenFly was not flown in these local coordinate tasks. Native external simulation and real-world readiness remain untested.",
    "",
    "## Evidence",
    "",
    "SeePROTOCOL.md,openfly_data_audit.json,*_training_report.json,*_transfer_report.json,summary.json,loss_curves.png,*_flight_audit.json andui_check.json. Originalbaselines/splits andheld-outseeds1-40/protected1060-1064 preserved.",
    "",
    "Review:http://127.0.0.1:8771/expanded_models.html",
]
(root / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
print("Finalreport written")

# Append a completion finding only after the final source/prediction UI audit.
assert (root / "ui_check.json").exists()
marker = b"D141 final execution complete:"
record = (
    b"\n\nD141 final execution complete: both expanded-data training jobs, all four official\n"
    b"OpenFly offline evaluations and audited Smol500/Qwen local flights finished.\n"
    b"Results and limits: reports/vla_expanded_models_20260917/REPORT.md.\n"
    b"No external training rows, AWS spending or native OpenFly flight-success claim.\n"
)
for filename in ("docs/RESEARCH_LOG.md", "CHANGES.md"):
    path = Path(filename)
    if marker not in path.read_bytes():
        with path.open("ab") as file:
            file.write(record)

# Commit only the task-owned completed evidence and its completion findings.
paths = [str(root), "docs/RESEARCH_LOG.md", "CHANGES.md"]
subprocess.run(["git", "add", *paths], check=True)
changed = subprocess.run(["git", "diff", "--cached", "--quiet", "--", *paths])
if changed.returncode == 1:
    subprocess.run(
        [
            "git",
            "commit",
            "--only",
            "-m",
            "Record expanded Smol500 Qwen and official OpenFly evaluation results",
            "--",
            *paths,
        ],
        check=True,
    )
elif changed.returncode != 0:
    raise RuntimeError("Could not verify completed evidence staging")
