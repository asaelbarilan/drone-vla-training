"""Label saved D139 viewers without changing immutable run IDs or model evidence."""

import json
import re
from pathlib import Path

ROOT = Path("D:/drone_vla_pilot/runs")
OUT = Path("reports/vla_dataset_review_20260916")


def label_page(source, destination, condition, model_label="Smol256"):
    text = source.read_text(encoding="utf-8")
    match = re.search(r"const DATA = (.*);\n", text)
    data = json.loads(match.group(1))
    for run in data["runs"]:
        mode = "trained" if "_trained_" in run["name"] else "zero-shot"
        run["display_name"] = f"{condition} | {model_label} | {mode} | seed {run['seed']}"
        counts = dict(motion=0, hold=0, stop=0, invalid=0)
        for decision in run["decisions"]:
            parsed = (decision.get("recording") or {}).get("parsed")
            kind = (
                "invalid"
                if parsed is None
                else "stop"
                if parsed["stop"]
                else "hold"
                if all(
                    parsed[k] == 32 for k in ("forward_bin", "right_bin", "down_bin", "yaw_cw_bin")
                )
                else "motion"
            )
            counts[kind] += 1
        run["execution_summary"] = (
            f"Recorded execution: {len(run['decisions'])} model calls; "
            f"{len(run['frames']) - 1} control intervals; "
            f"{run['frames'][-1]['t']:.2f} simulated seconds. "
            f"Predictions: {counts['motion']} motion, {counts['hold']} HOLD, "
            f"{counts['stop']} STOP, {counts['invalid']} invalid. "
            "HOLD means zero commanded motion while the episode continues. STOP ends the episode. "
            "A stationary replay can be a model failure; watch the clock and inspect predictions."
        )
    blob = json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    text = text[: match.start(1)] + blob + text[match.end(1) :]
    text = text.replace(
        "${r.name} · ${r.result.termination_reason}",
        "${r.display_name} · ${r.result.termination_reason}",
    )
    text = text.replace(
        "<title>Flight debugger · UAV Lab</title>",
        f"<title>{condition} data | {model_label} flights</title>",
    )
    text = text.replace(
        "<h1>Flight debugger</h1>", f"<h1>{condition} data · {model_label} flights</h1>"
    )
    text = text.replace(
        '<div class="stats">',
        '<div class="card pad" id="executionSummary" style="margin-bottom:14px"></div>'
        '<div class="stats">',
        1,
    )
    text = text.replace(
        "function seek(i,follow=true){",
        "function seek(i,follow=true){text('executionSummary',run.execution_summary);",
    )
    text = text.replace("'flight-note:'+run.name", "'flight-note:'+location.pathname+':'+run.name")
    destination.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    for key, condition in (("control", "Original"), ("expanded", "Expanded")):
        label_page(
            ROOT / f"smol256_balanced_{key}_20260917_a_flights/model_flights.html",
            OUT / f"balanced_{key}_flights.html",
            condition,
        )
