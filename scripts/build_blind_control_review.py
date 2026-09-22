# ruff: noqa: E501
"""D152 blind control: score real versus gray images on the full aligned 72 panel.

The question is narrow. If replacing every input frame with flat gray does not
change a model's answers, that model is not reading the camera, and its rank on
the direction-agreement table describes its text prior rather than its grounding.
Accuracy alone cannot show this, so the paired change count and McNemar counts
are reported beside it.
"""

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_blind_control_20260920"
REPAIR = ROOT / "reports/vla_openfly_repair_20260918"
VIEW = ROOT / "reports/vla_dataset_review_20260916"
MODELS = ("openfly_vla", "smol256", "smol500", "qwen")
LABELS = [
    "STOP",
    "forward 3 m",
    "left turn",
    "right turn",
    "up 3 m",
    "down 3 m",
    "left",
    "right",
    "forward 6 m",
    "forward 9 m",
]


def direction(a):
    """Collapse the 6 m and 9 m forward commands onto forward, as D147 scored them."""
    return 1 if a in (8, 9) else a


def wilson(correct, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = correct / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(centre - half, 4), round(centre + half, 4)


def mcnemar_p(b, c):
    """Exact two-sided binomial test on the discordant pairs."""
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return round(min(1.0, 2 * tail), 4)


def load_predictions(model, condition):
    """Return {decision_id: {action_id, raw}} for one model under one image condition."""
    if model == "openfly_vla":
        probe = json.loads((OUT / f"openfly_{condition}/probe.json").read_text(encoding="utf-8"))
        assert probe["status"] == "inference_complete"
        assert all(o["generated_token_count"] == 8 for o in probe["outputs"]), "early EOS"
        return {
            o["decision_id"].removeprefix("gray:"): dict(
                action_id=o["strict_decoded"]["action_id"],
                raw=json.dumps(o["strict_decoded"]),
            )
            for o in probe["outputs"]
        }
    data = json.loads((OUT / f"{model}_{condition}.json").read_text(encoding="utf-8"))
    assert data["status"] == "complete"
    return {
        o["id"].removeprefix("gray:"): dict(action_id=o["action_id"], raw=o["raw"])
        for o in data["outputs"]
    }


def score(targets, preds):
    matrix = [[0] * 7 for _ in range(6)]
    for t, p in zip(targets, preds, strict=True):
        matrix[t][p if p in range(6) else 6] += 1
    correct = sum(p == t for t, p in zip(targets, preds, strict=True))
    return dict(
        n=len(targets),
        correct=correct,
        valid=sum(p is not None for p in preds),
        accuracy=round(correct / len(targets), 4),
        ci95=wilson(correct, len(targets)),
        distinct_answers=len({str(p) for p in preds}),
        per_action=[
            dict(action=LABELS[a], correct=matrix[a][a], n=sum(matrix[a])) for a in range(6)
        ],
        confusion=matrix,
    )


def main():
    panel = [
        json.loads(s) for s in (OUT / "real_panel.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(panel) == 72
    source = REPAIR / "aligned_panel.jsonl"
    targets = [direction(r["action_id"]) for r in panel]

    # The adapters emit 3 m forward only, so an always-forward answer is the
    # trivial reference this panel must beat: 12 of 72 by construction.
    always_forward = sum(t == 1 for t in targets)

    results, cases = {}, []
    preds = {m: {c: load_predictions(m, c) for c in ("real", "gray")} for m in MODELS}
    for model in MODELS:
        real = [preds[model]["real"][r["id"]]["action_id"] for r in panel]
        gray = [preds[model]["gray"][r["id"]]["action_id"] for r in panel]
        real_d = [None if a is None else direction(a) for a in real]
        gray_d = [None if a is None else direction(a) for a in gray]
        changed = sum(a != b for a, b in zip(real, gray, strict=True))
        b = sum(p == t and q != t for p, q, t in zip(real_d, gray_d, targets, strict=True))
        c = sum(p != t and q == t for p, q, t in zip(real_d, gray_d, targets, strict=True))
        results[model] = dict(
            real=score(targets, real_d),
            gray=score(targets, gray_d),
            changed_when_blinded=changed,
            changed_fraction=round(changed / len(panel), 4),
            mcnemar=dict(real_only=b, gray_only=c, p=mcnemar_p(b, c)),
        )

    for row, target in zip(panel, targets, strict=True):
        cases.append(
            dict(
                id=row["id"],
                trajectory=row["trajectory"],
                environment=row["trajectory"].split("/")[0],
                frame_index=row["frame_index"],
                instruction=row["instruction"],
                action_id=row["action_id"],
                target=target,
                previews=["repair_assets/" + s[:20] + ".jpg" for s in row["image_sha256"]],
                outputs={m: {c: preds[m][c][row["id"]] for c in ("real", "gray")} for m in MODELS},
            )
        )

    routes = defaultdict(list)
    for i, case in enumerate(cases):
        routes[case["trajectory"]].append(i)
    route_list = [
        dict(
            trajectory=t,
            environment=t.split("/")[0],
            indices=sorted(routes[t], key=lambda i: cases[i]["frame_index"]),
        )
        for t in sorted(routes)
    ]

    adapter_prompt = (
        json.loads((OUT / "smol256_real.json").read_text(encoding="utf-8"))["outputs"][0]["prompt"]
        .split("Route: ")[0]
        .strip()
    )
    openfly_probe = json.loads((OUT / "openfly_real/probe.json").read_text(encoding="utf-8"))

    payload = dict(
        summary=dict(
            status="complete",
            adapter_prompt_prefix=adapter_prompt,
            openfly_prompt_style=openfly_probe["prompt_style"],
            prompt_display=chr(10).join(
                [
                    "our adapters (smol256, smol500, qwen):",
                    adapter_prompt,
                    "Route: <route instruction>",
                    "",
                    "openfly_vla (" + openfly_probe["prompt_style"] + " style):",
                    "<route instruction>",
                ]
            ),
            prompt_note=(
                "The two families are not asked the same way. Our adapters receive the task "
                "framing above followed by 'Route: <instruction>' and must reply with one digit. "
                "openfly_vla receives the route instruction alone, in its published model-card "
                "style, and emits action tokens."
            ),
            panel="aligned 72 decisions, 12 per recorded direction, 21 routes, 11 environments",
            n=len(panel),
            routes=len(route_list),
            chance=always_forward,
            always_forward_reference=always_forward,
            results=results,
            panel_sha256=hashlib.sha256((OUT / "real_panel.jsonl").read_bytes()).hexdigest(),
            gray_panel_sha256=hashlib.sha256((OUT / "gray_panel.jsonl").read_bytes()).hexdigest(),
            source_panel_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        ),
        cases=cases,
        routes=route_list,
        labels=LABELS,
    )
    (OUT / "summary.json").write_text(json.dumps(payload["summary"], indent=2), encoding="utf-8")
    (VIEW / "blind_control.json").write_text(json.dumps(payload), encoding="utf-8")
    (VIEW / "blind_control.html").write_text(PAGE, encoding="utf-8")

    missing = [p for c in cases for p in c["previews"] if not (VIEW / p).is_file()]
    assert not missing, f"{len(missing)} preview images absent"
    print(
        json.dumps(
            {
                m: {
                    "real": r["real"]["correct"],
                    "gray": r["gray"]["correct"],
                    "changed": r["changed_when_blinded"],
                }
                for m, r in results.items()
            },
            indent=1,
        )
    )


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Blind control</title><style>
body{background:#102033;color:#edf4ff;font:17px system-ui;max-width:1150px;margin:25px auto;padding:0 18px;line-height:1.5}
section{background:#1b3048;padding:20px;border-radius:10px;margin:18px 0}
a{color:#84cfff}.warning{color:#ffce8b}.muted{color:#a8bdd4;font-size:15px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}
td,th{padding:8px;text-align:left;border-bottom:1px solid #5a6c80;white-space:nowrap}
select{max-width:100%;padding:10px;background:#213b55;color:white;border-radius:6px;border:1px solid #5a6c80}
pre{white-space:pre-wrap;overflow-wrap:anywhere}
.images{display:flex;gap:8px;margin:8px 0}.images img{width:32%;border-radius:6px}
.step{background:#16283d;padding:14px;border-radius:9px;margin:14px 0;border-left:4px solid #3d5a7d}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.card{background:#263e58;padding:10px;border-radius:8px;font-size:15px}
.hit{color:#8ce8a8}.miss{color:#ff9d9d}.same{color:#ffce8b;font-size:14px}.diff{color:#8ce8a8;font-size:14px}
b.name{font-size:14px;color:#cfe4ff}
.ask{background:#0d1c2e;border:1px solid #3d5a7d;border-radius:8px;padding:11px 13px;margin:0 0 12px;font-size:15px;color:#e4eefb}
.tag{display:inline-block;background:#3d5a7d;color:#dcebff;font-size:12px;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;border-radius:5px;margin-right:8px;vertical-align:1px}
#prompts{background:#16283d;padding:13px;border-radius:8px;font-size:14px;color:#cfe4ff;white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:700px){.grid{grid-template-columns:1fr 1fr}.images img{width:32%}}
</style>
<h1>Do these models read the camera?</h1>
<section class="warning"><b>One question only.</b> Every model answered the same 72 decisions twice: once with the real frames, once with every frame replaced by flat gray. If blinding a model does not change its answers, that model is not using the image, and its position in the direction-agreement table reflects its text prior. This page is not a flight benchmark.</section>
<section><h2>Result</h2><div class="scroll"><table id="scores"></table></div>
<p class="muted" id="ref"></p>
<p class="muted"><b>Changed</b> counts how many of the 72 answers moved when the images were blinded — the direct measure of whether pixels reach the decision. <b>Distinct</b> is how many different answers a model produced across 72 different images. McNemar <i>p</i> tests the paired real-versus-gray accuracy difference; above 0.05 the difference is not separable from noise at this panel size.</p></section>
<section><h2>What each model is asked</h2>
<p class="muted" id="promptnote"></p><div id="prompts"></div>
<p class="muted">The route instruction below each step is appended to this framing, and it is the only part that changes between steps within a route.</p></section>
<section><h2>Every decision, by route</h2>
<p class="muted">21 recorded routes across 11 environments. Each step shows the three causal frames the model received, the recorded command, and all four models under both conditions.</p>
<select id="route"></select><div id="steps"></div></section>
<section><h2>Provenance</h2><pre id="prov" class="muted"></pre></section>
<p><a href="openfly_repair.html">D147 decoder and alignment</a> · <a href="openfly_routes.html">Source-matched route debugger</a></p>
<script>
const $=id=>document.getElementById(id);let D;
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const name=a=>a===null||a===undefined?'INVALID':D.labels[a];
function dir(a){return a===8||a===9?1:a}
function rows(){
 const s=D.summary,h='<tr><th>Model</th><th>Real /72</th><th>Gray /72</th><th>Changed /72</th><th>Valid real</th><th>Distinct real</th><th>McNemar p</th></tr>';
 $('scores').innerHTML=h+Object.entries(s.results).map(([m,r])=>
  `<tr><td>${m}</td><td>${r.real.correct}</td><td>${r.gray.correct}</td><td>${r.changed_when_blinded}</td><td>${r.real.valid}</td><td>${r.real.distinct_answers}</td><td>${r.mcnemar.p}</td></tr>`).join('');
 $('ref').textContent='Always-forward reference: '+s.always_forward_reference+'/72. The panel is balanced at 12 examples per recorded direction, so a constant answer scores 12.';
 $('promptnote').textContent=s.prompt_note;
 $('prompts').textContent=s.prompt_display;
 $('prov').textContent=JSON.stringify({panel:s.panel,panel_sha256:s.panel_sha256,gray_panel_sha256:s.gray_panel_sha256,source_panel_sha256:s.source_panel_sha256},null,1);
}
function steps(){
 const r=D.routes[+$('route').value||0];
 $('steps').innerHTML=r.indices.map(i=>{
  const c=D.cases[i];
  const cards=Object.entries(c.outputs).map(([m,o])=>{
   const cell=(p)=>{const ok=p.action_id!==null&&dir(p.action_id)===c.target;
    return `<div class="${ok?'hit':'miss'}">${esc(name(p.action_id))}</div>`};
   const moved=o.real.action_id!==o.gray.action_id;
   return `<div class="card"><b class="name">${m}</b>
    <div class="muted">real</div>${cell(o.real)}
    <div class="muted">gray</div>${cell(o.gray)}
    <div class="${moved?'diff':'same'}">${moved?'changed when blinded':'same when blinded'}</div></div>`}).join('');
  return `<div class="step"><p class="ask"><span class="tag">asked</span> ${esc(c.instruction)}</p>
   <div class="images">${c.previews.map(p=>`<img src="${p}" loading="lazy" alt="Causal source frame">`).join('')}</div>
   <p><b>Recorded command:</b> ${esc(name(c.action_id))} <span class="muted">· frame ${c.frame_index}</span></p>
   <div class="grid">${cards}</div></div>`}).join('');
}
fetch('blind_control.json').then(r=>r.json()).then(d=>{D=d;rows();
 $('route').innerHTML=d.routes.map((r,i)=>`<option value="${i}">${i+1}/${d.routes.length}: ${esc(r.environment)} · ${r.indices.length} step${r.indices.length>1?'s':''}</option>`).join('');
 $('route').onchange=steps;steps()});
</script></html>"""

if __name__ == "__main__":
    main()
