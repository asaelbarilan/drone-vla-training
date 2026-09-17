"""Portable admitted-data review with exact source images and effective batches."""

# ruff: noqa: E501
import argparse
import base64
import json
from pathlib import Path

from uavlab.training.mixed_batches import task_class


def build(data, reports, out):
    manifest = json.loads((data / "manifest.json").read_text())
    rows = [json.loads(s) for s in (data / "index.jsonl").read_text().splitlines()]
    display = []
    for row in rows:
        if row["seed"] < 1450:
            continue
        image = base64.b64encode(
            (Path(row["data_root"]) / row["images"]["mosaic"]).read_bytes()
        ).decode()
        display.append(
            dict(
                id=row["decision_id"],
                seed=row["seed"],
                split=row["split"],
                group=task_class(row),
                instruction=row["instruction"],
                state=row["state"],
                target=row["target"],
                image=image,
            )
        )
    payload = json.dumps(
        dict(rows=display, counts=manifest["counts"], batches=manifest["schedules"]["expanded"][:8])
    ).replace("</", r"<\/")
    html = """<!doctype html><html><meta charset="utf-8"><title>Expanded local training data</title>
<style>body{font:17px system-ui;background:#101723;color:#edf3fa;max-width:1100px;margin:auto;padding:24px}a{color:#79c6ff}select{max-width:100%;padding:10px}img{width:448px;max-width:100%;image-rendering:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#1d2838;padding:16px}section{display:flex;gap:24px;flex-wrap:wrap}section>div{flex:1;min-width:260px}</style>
<h1>Expanded local simulation data</h1><p>Teacher demonstrations, not trained model predictions. 1,156 TRAIN / 300 VAL. Original 84 VAL rows preserved. No real-world or external-simulator data.</p>
<p><a href="expanded_teacher_flights.html">Replay the 20 new coordinate teacher flights</a> (raw source logs retain the earlier FLU encoding; the training targets below use FRD).</p>
<label>New admitted example <select id="sample"></select></label>
<section><div><img id="image" alt="Exact front-above-down source mosaic"><p id="meta"></p></div><div><p id="instruction"></p><pre id="state"></pre><pre id="target"></pre><p id="physical"></p></div></section>
<h2>Actual scheduled effective batches</h2><p>One visual turn + one navigation + one HOLD + one STOP. Four sequential microbatches, loss divided by four, one optimizer step. This deliberately oversamples rare tasks.</p><pre id="batches"></pre>
<p>Bounds: varied distances/headings and visible target geometry in the same simple renderer. No obstacle avoidance, external-domain transfer, or real-flight readiness claim.</p>
<script>const DATA=PAYLOAD;
const select=document.querySelector('#sample');
DATA.rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${r.split} | ${r.group} | ${r.id}`;select.append(o)});
function show(){const r=DATA.rows[Number(select.value)];document.querySelector('#image').src='data:image/png;base64,'+r.image;document.querySelector('#meta').textContent=`Seed ${r.seed} / ${r.split} / ${r.group}`;document.querySelector('#instruction').textContent=r.instruction;document.querySelector('#state').textContent=JSON.stringify(r.state,null,2);document.querySelector('#target').textContent=JSON.stringify(r.target,null,2);const t=r.target;document.querySelector('#physical').textContent=`Heading-level forward/right/down: ${((t.forward_bin-32)*10/64).toFixed(3)}, ${((t.right_bin-32)*10/64).toFixed(3)}, ${((t.down_bin-32)*10/64).toFixed(3)} m/s. Clockwise yaw: ${((t.yaw_cw_bin-32)*3/64).toFixed(3)} rad/s. STOP: ${t.stop} (mission termination, not landing).`}
select.onchange=show;show();document.querySelector('#batches').textContent=JSON.stringify(DATA.batches,null,2);
</script></html>""".replace("PAYLOAD", payload)
    out.write_text(html, encoding="utf-8")
    (out.parent / "expanded_teacher_flights.html").write_bytes(
        (reports / "coordinate/teacher_flights.html").read_bytes()
    )
    return len(display)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--reports", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(build(a.data, a.reports, a.out))
