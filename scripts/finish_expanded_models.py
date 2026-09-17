"""Wait for the frozen local training queue, then evaluate sequentially and publish."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("D:/drone_vla_pilot")
RUNS = BASE / "runs"
REPORTS = ROOT / "reports/vla_expanded_models_20260917"
VIEW = ROOT / "reports/vla_dataset_review_20260916"
PY = BASE / "venv_qwen/Scripts/python.exe"
OPENFLY = BASE / "venv_openfly/Scripts/python.exe"
NAMES = {
    "smol256": "smol256_balanced_expanded_20260917_a",
    "smol500": "smol500_expanded_20260917_a",
    "qwen": "qwen_expanded_20260917_a",
}
env = dict(
    os.environ,
    PYTHONPATH=str(ROOT / "src"),
    USE_TF="0",
    HF_HOME=str(BASE / "hf_cache"),
    TEMP=str(BASE / "pip_cache"),
    TMP=str(BASE / "pip_cache"),
)


def run(script, *args, python=PY):
    print(json.dumps(dict(event="start", script=script, args=[str(a) for a in args])), flush=True)
    subprocess.run(
        [str(python), str(ROOT / "scripts" / script), *map(str, args)],
        cwd=ROOT,
        env=env,
        check=True,
    )


start = time.monotonic()
while True:
    statuses = {}
    for model in ("smol500", "qwen"):
        p = RUNS / NAMES[model] / "report.json"
        try:
            statuses[model] = json.loads(p.read_text())["status"]
        except (FileNotFoundError, json.JSONDecodeError):
            statuses[model] = "pending"
    if "failed" in statuses.values():
        raise RuntimeError(
            f"Training failed; preserve artifacts and inspect before evaluation: {statuses}"
        )
    active = False
    for process in psutil.process_iter(["name", "cmdline"]):
        if not (process.info["name"] or "").lower().startswith("python"):
            continue
        cmd = " ".join(process.info["cmdline"] or [])
        if "run_balanced_local_vla.py" in cmd and any(NAMES[m] in cmd for m in ("smol500", "qwen")):
            active = True
    run("build_expanded_models_review.py")
    if all(s == "complete" for s in statuses.values()) and not active:
        break
    assert time.monotonic() - start < 19800, "Training wait exceeded5.5hours"
    time.sleep(30)

run(
    "probe_openfly_local.py",
    "--eval-data",
    BASE / "data/openfly_eval_20260917/eval.jsonl",
    "--prompt-style",
    "training",
    "--out",
    RUNS / "openfly_official_eval_20260917",
    python=OPENFLY,
)
run("build_expanded_models_review.py")
for model in ("smol256", "smol500", "qwen"):
    adapter = RUNS / NAMES[model] / "adapter_s400"
    run(
        "evaluate_openfly_transfer.py",
        "--model",
        model,
        "--adapter",
        adapter,
        "--out",
        RUNS / f"{model}_openfly_transfer_20260917",
    )
    run("build_expanded_models_review.py")
for model in ("smol500", "qwen"):
    folder = RUNS / f"{model}_expanded_20260917_a_flights"
    run(
        "evaluate_local_vla_pair.py",
        "--model",
        model,
        "--label",
        "mixed",
        "--modes",
        "trained",
        "--data",
        BASE / "data/public_goal_fixture_20260916_v1",
        "--adapter",
        RUNS / NAMES[model] / "adapter_s400",
        "--out",
        folder,
    )
    run(
        "audit_local_vla_pair.py", "--runs", folder, "--out", REPORTS / f"{model}_flight_audit.json"
    )
    shutil.copyfile(folder / "summary.json", REPORTS / f"{model}_flight_summary.json")
    from label_balanced_flights import label_page

    label_page(
        folder / "model_flights.html", VIEW / f"{model}_expanded_flights.html", "Expanded", model
    )
    ui = REPORTS / f"{model}_flight_ui"
    ui.mkdir(exist_ok=True)
    run(
        "check_local_vla_debugger.py",
        "--runs",
        folder,
        "--url",
        f"http://127.0.0.1:8771/{model}_expanded_flights.html",
        "--out",
        ui,
        python="python",
    )
run("build_expanded_models_review.py")
run("check_expanded_models_review.py", python="python")
run("write_expanded_models_report.py")
(REPORTS / "pipeline_complete.json").write_text(
    json.dumps(
        dict(status="complete", wall_seconds=time.monotonic() - start, aws_spend=0), indent=2
    )
)
print("D141_EVALUATION_COMPLETE", flush=True)
