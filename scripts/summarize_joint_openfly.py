# ruff: noqa: E501
"""D144 independent result audit and static plots; refuses incomplete pilot results."""

import collections
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from run_joint_openfly_queue import MODELS, NAMES, REPORT, RUNS, metrics, write

from uavlab.training.direct_vla_frd import parse_target, target_json


def main():
    data = Path("D:/drone_vla_pilot/data/joint_openfly_local_20260917_v1")
    manifest = json.loads((data / "manifest.json").read_text())
    assert (
        hashlib.sha256((data / "index.jsonl").read_bytes()).hexdigest() == manifest["index_sha256"]
    )
    by = {r["id"]: r for r in map(json.loads, (data / "index.jsonl").read_text().splitlines())}
    frozen = json.loads((REPORT / "data_audit.json").read_text())
    assert manifest == frozen, "frozen admission audit changed"
    native_train = [r for r in by.values() if r["source"] == "openfly" and r["split"] == "train"]
    native_val = [r for r in by.values() if r["source"] == "openfly" and r["split"] == "val"]
    train_routes = {r["trajectory"] for r in native_train}
    val_routes = {r["trajectory"] for r in native_val}
    assert len(train_routes) == 88 and len(val_routes) == 22 and not train_routes & val_routes
    official = Path("D:/drone_vla_pilot/data/openfly_eval_20260917/Annotation")
    official_routes = {
        e["image_path"]
        for split in ("seen", "unseen")
        for e in json.loads((official / (split + ".json")).read_text())
    }
    assert len(official_routes) == 3000
    assert not (train_routes | val_routes) & official_routes
    assert not {h for r in native_train for h in r["image_sha256"]} & {
        h for r in native_val for h in r["image_sha256"]
    }
    for row in by.values():
        if row["source"] == "local":
            assert row["seed"] not in set(range(1, 41)) | set(range(1060, 1065))
        else:
            assert row["action_id"] in range(6)
            assert row["action_id"] == 0 or row["next_pose_verified"]
    queue = json.loads((REPORT / "queue_status.json").read_text())
    assert queue["status"] == "complete" and queue["completed"] == list(MODELS), (
        "Queue has not completed"
    )
    summary = {}
    fig, axes = plt.subplots(3, 2, figsize=(12, 12), constrained_layout=True)
    colors = {"local": "#1678b4", "openfly": "#d47712"}
    for index, model in enumerate(MODELS):
        run = RUNS / f"{model}_joint_20260917_a"
        r = json.loads((run / "report.json").read_text())
        assert r["status"] == "complete" and r["updates"] == 400 and r["reload_matches"]
        assert r["data_sha256"] == manifest["index_sha256"]
        assert r["training_schedule"] == manifest["schedules"]
        assert r["evaluation_ids"] == manifest["evaluation_ids"]
        assert [x["step"] for x in r["losses"]] == list(range(1, 401))
        assert [x["step"] for x in r["comparable_losses"]] == [0, 100, 200, 300, 400]
        for step, entry in enumerate(r["losses"]):
            assert entry["sample_ids"] == manifest["schedules"][step]
            assert all(by[k]["split"] == "train" for k in entry["sample_ids"])
            assert math.isfinite(entry["loss"]) and entry["gradient_norm"] > 0
            assert math.isfinite(entry["gradient_norm"])
            assert math.isclose(entry["loss"], sum(entry["domain_losses"].values()) / 2)
        for phase in ("before", "after"):
            assert [p["id"] for p in r[phase]] == manifest["evaluation_ids"]
            for p in r[phase]:
                row = by[p["id"]]
                if row["source"] == "openfly":
                    target = row["action_id"]
                    raw = p["raw"].strip()
                    parsed = int(raw) if raw in {str(i) for i in range(6)} else None
                else:
                    target = row["target"]
                    try:
                        parsed = json.loads(target_json(parse_target(p["raw"])))
                    except (ValueError, TypeError, KeyError):
                        parsed = None
                assert p["target"] == target and p["parsed"] == parsed
                assert p["valid"] == (parsed is not None) and p["exact"] == (parsed == target)
        assert len(r["reload_checks"]) == 4
        after = {p["id"]: p for p in r["after"]}
        assert all(after[p["id"]]["raw"] == p["raw"] for p in r["reload_checks"])
        adapter = run / "adapter_s400/adapter_model.safetensors"
        assert adapter.stat().st_size > 0
        flights = json.loads((RUNS / f"{model}_joint_flights_20260917_a/summary.json").read_text())
        audit = json.loads((REPORT / f"{model}_flight_audit.json").read_text())
        browser = json.loads((REPORT / f"{model}_flight_browser/model_ui_check.json").read_text())
        assert len(flights["results"]) == 2
        assert {f["seed"] for f in flights["results"]} == {1400, 1405}
        assert all(f["mode"] == "trained" for f in flights["results"])
        assert audit["no_teacher_control_substitution"] and len(audit["runs"]) == 2
        assert browser["playback"] and browser["responsive"] and not browser["js_errors"]
        for a, f in zip(
            sorted(audit["runs"], key=lambda x: x["seed"]),
            sorted(flights["results"], key=lambda x: x["seed"]),
            strict=True,
        ):
            assert a["seed"] == f["seed"]
            assert a["checked_original_mosaics_and_prompts"] == f["model_calls"]
            assert a["result"]["termination_reason"] == f["termination_reason"]
            assert a["replay"]["missing_source_frames"] == 0
            assert a["replay"]["max_position_error_m"] < 1e-8
        summary[model] = dict(
            metrics={phase: metrics(r[phase]) for phase in ("before", "after")},
            comparable_losses=r["comparable_losses"],
            adapter_sha256=hashlib.sha256(adapter.read_bytes()).hexdigest(),
            elapsed_seconds=r["elapsed_seconds"],
            peak_allocated_gib=r["peak_allocated_gib"],
            flights=[
                {
                    k: f[k]
                    for k in ("seed", "success", "termination_reason", "metrics", "model_calls")
                }
                for f in flights["results"]
            ],
            native_confusion={
                NAMES[a]: dict(
                    collections.Counter(
                        "INVALID" if p["parsed"] is None else NAMES[p["parsed"]]
                        for p in r["after"]
                        if p["source"] == "openfly" and p["target"] == a
                    )
                )
                for a in range(6)
            },
        )
        for source, color in colors.items():
            values = [e["domain_losses"][source] for e in r["losses"]]
            smooth = [sum(values[max(0, i - 19) : i + 1]) / min(i + 1, 20) for i in range(400)]
            axes[index, 0].plot(range(1, 401), smooth, color=color, label=source)
            for split, style in (("train", "--"), ("val", "-")):
                axes[index, 1].plot(
                    [e["step"] for e in r["comparable_losses"]],
                    [e["values"][source + ":" + split] for e in r["comparable_losses"]],
                    style,
                    marker="o",
                    color=color,
                    label=source + " " + split,
                )
        axes[index, 0].set_title(model + " / optimization loss (20-update mean)")
        axes[index, 1].set_title(model + " / fixed-probe evaluation-mode loss")
        for axis in axes[index]:
            axis.set_xlabel("Optimizer update")
            axis.set_ylabel("Action-weighted token loss")
            axis.grid(alpha=0.25)
            axis.legend(fontsize=8)
    fig.suptitle("D144: OpenFly + local training — losses compared within each model/source")
    fig.savefig(REPORT / "loss_curves.png", dpi=160)
    fig.savefig(REPORT / "loss_curves.pdf")
    plt.close(fig)
    write(REPORT / "summary.json", summary)
    lines = [
        "# D144 — Joint OpenFly/local three-model pilot",
        "",
        "All three local runs completed 400 updates with separate saved/reloaded adapters.",
        "No AWS spending. This completes the bounded experiment, not real-world qualification.",
        "",
        "## Frozen held-out action results",
        "",
        "| Model | Native base exact | Native trained exact | Native macro recall | Native valid | False STOP / 60 nonterminal | Local trained exact | Local valid |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in summary.items():
        base = result["metrics"]["before"]["openfly"]
        native = result["metrics"]["after"]["openfly"]
        local = result["metrics"]["after"]["local"]
        lines.append(
            f"|{name}|{base['exact']}/72|{native['exact']}/72|{native['macro_recall']:.1%}|{native['valid']}/72|{native['false_stop']}/60|{local['exact']}/28|{local['valid']}/28|"
        )
    lines += [
        "",
        "Native panel: 12 examples for each of six actions; always-forward reference12/72",
        "and macro recall16.7%. These are held-out routes selected from official TRAIN,",
        "not the full official seen/unseen benchmark. Local panel is28 preserved cases,",
        "not all300 local validation rows. Full per-class confusion is in summary.json.",
        "Base format failures and exact JSON mismatches are not flight-success measures.",
        "",
        "## Actual local simulation flights",
        "",
    ]
    for name, result in summary.items():
        for f in result["flights"]:
            lines.append(
                f"- {name}, seed{f['seed']}: {f['termination_reason']}; success={f['success']}; distance={f['metrics']['distance_to_goal_m']:.3f}m; {f['model_calls']} actual model calls."
            )
    lines += [
        "",
        "Each model controls two local development flights, with simulation paused",
        "during inference. Audits verify actual answers, source images, decoded controls",
        "and replayed positions. Two flights/model are diagnostic, not statistical evidence.",
        "OpenFly source clips are recorded dataset observations, not native model rollouts.",
        "",
        "## Interpretation limits",
        "",
        "110 OpenFly routes:88TRAIN/22dev,2929/815 admitted decisions;8 inconsistent",
        "motion labels quarantined. Local1156TRAIN/300VAL unchanged. Same400-update",
        "schedule/model, four examples/source/update,1600 exposures/source; actual unique",
        "coverage592native examples across all88TRAIN routes and790local examples.",
        "Native classes are deliberately oversampled; repeated rare actions are not new data.",
        "Native3m/30-degree primitives and local FRD velocity JSON retain explicit separate",
        "instruction contracts. No guessed OpenFly velocity/duration labels were introduced.",
        "Smol uses BF16 and QwenNF4, with different tokenizers/processors; absolute token",
        "loss magnitudes are not cross-model quality rankings. No checkpoint selection",
        "used validation; final400-step adapters are the evaluated outputs.",
        "Real-time control, native OpenFly closed-loop transfer, physical drone data",
        "coverage and real-world deployment remain open. Do not infer readiness from loss.",
        "",
        "## Evidence",
        "",
        "PROTOCOL.md; data_audit.json; preflight.json; exposure_audit.json;",
        "*_training_report.json; *_flight_audit.json; *_flight_browser/model_ui_check.json;",
        "summary.json; loss_curves.png/PDF. All original baselines and protected seeds preserved.",
        "Live review: http://127.0.0.1:8771/joint_openfly.html",
        "",
    ]
    (REPORT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    write(
        REPORT / "completion_audit.json",
        dict(
            models=list(MODELS),
            updates=1200,
            examples_processed=9600,
            raw_predictions_reparsed=600,
            reload_spots=12,
            local_flights=6,
            schedule_and_split_match=True,
            finite_gradients_and_losses=True,
            flight_source_control_and_browser_checks=True,
            no_official_eval_or_protected_local_training=True,
            claim="Bounded training/evaluation completed; deployment readiness not established",
        ),
    )
    print(json.dumps({k: v["metrics"]["after"]["openfly"] for k, v in summary.items()}))


if __name__ == "__main__":
    main()
