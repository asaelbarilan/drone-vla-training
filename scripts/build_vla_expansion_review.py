# ruff: noqa: E501
"""Build an offline, native-schema review of visual pairs and external flight previews."""

import argparse
import base64
import hashlib
import json
from pathlib import Path


def data_url(path):
    return (
        "data:image/"
        + ("png" if path.suffix == ".png" else "jpeg")
        + ";base64,"
        + base64.b64encode(path.read_bytes()).decode()
    )


def build(visual, external, out):
    episodes = []
    rows = [json.loads(s) for s in (visual / "index.jsonl").read_text().splitlines()]
    for r in rows:
        episodes.append(
            dict(
                name=f"Local / s{r['seed']} / layout{r['layout']} / {r['instruction_colour']} / {r['split']}",
                instruction=r["instruction"],
                kind="Synthetic visible-target teacher segment. Not a learned flight.",
                frames=[
                    data_url(visual / r["images"]["mosaic"]),
                    data_url(visual / r["after_image"]),
                ],
                records=[
                    dict(
                        phase="Before", target=r["target"], state=r["state"], controls=r["controls"]
                    ),
                    dict(
                        phase="After 0.2 simulated seconds",
                        state=r["after_state"],
                        bearing_cw_rad=r["after_bearing_cw_rad"],
                    ),
                ],
            )
        )
    report = json.loads((external / "report.json").read_text())
    for src in report["sources"]:
        for i, ep in enumerate(src["episodes"]):
            log = json.loads(
                (
                    external / src["dataset"].split("/")[-1] / f"episode_{i:02d}" / "log.json"
                ).read_text()
            )
            frames = []
            for image in ep["images"]:
                path = external / image["path"]
                assert hashlib.sha256(path.read_bytes()).hexdigest() == image["sha256"]
                frames.append(data_url(path))
            episodes.append(
                dict(
                    name=f"{src['dataset'].split('/')[-1]} / {ep['id']} / source TRAIN",
                    instruction=ep["instruction"],
                    kind="Recorded HF viewer preview. Not live; not admitted to action training. Native log units/frame/timing unverified.",
                    frames=frames,
                    records=[
                        dict(frame_idx=j, raw_log=raw, preprocessed_log=log["preprocessed_logs"][j])
                        for j, raw in enumerate(log["raw_logs"])
                    ],
                )
            )
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VLA data expansion review</title><style>body{font:16px system-ui;margin:24px;background:#101827;color:#e4edf8}main{max-width:1100px;margin:auto}select{width:100%;padding:10px}button{padding:9px}#scrub{width:65%}.grid{display:grid;grid-template-columns:minmax(240px,1fr) minmax(240px,1fr);gap:20px}img{width:100%;image-rendering:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#1d2a3d;padding:15px}p{line-height:1.5}a{color:#8cd5ff}@media(max-width:650px){.grid{grid-template-columns:1fr}body{margin:12px}}</style><main><h1>Data expansion review</h1><p>64 local teacher segments + 10 recorded external flight previews. External data has no verified direct-control mapping and is excluded from training.</p><select id="episode"></select><h2 id="instruction"></h2><p id="kind"></p><button id="play">Play preview</button> <input id="scrub" type="range" min="0" value="0"> <span id="position"></span><p>Playback uses a fixed 5 frames/second for inspection; this is not a claim about source timing. Local segments show before/after only.</p><div class="grid"><img id="image" alt="Exact saved source frame"><pre id="record"></pre></div><p><a href="frd_comparison.html">Model flight comparison</a> · <a href="viewer.html">Original data fixture</a></p></main><script>const DATA=__DATA__;const sel=document.getElementById('episode'),scrub=document.getElementById('scrub');let timer=null;DATA.forEach((e,i)=>{const o=document.createElement('option');o.value=i;o.textContent=e.name;sel.append(o)});function draw(){const e=DATA[Number(sel.value)],i=Number(scrub.value);document.getElementById('instruction').textContent=e.instruction;document.getElementById('kind').textContent=e.kind;document.getElementById('image').src=e.frames[i];document.getElementById('record').textContent=JSON.stringify(e.records[i],null,2);document.getElementById('position').textContent=`${i+1} / ${e.frames.length}`;}function stop(){clearInterval(timer);timer=null;document.getElementById('play').textContent='Play preview';}sel.onchange=()=>{stop();scrub.max=DATA[Number(sel.value)].frames.length-1;scrub.value=0;draw()};scrub.oninput=draw;document.getElementById('play').onclick=()=>{if(timer){stop();return}document.getElementById('play').textContent='Pause';timer=setInterval(()=>{if(Number(scrub.value)>=Number(scrub.max)){stop();return}scrub.value=Number(scrub.value)+1;draw()},200)};sel.onchange();</script></html>"""
    out.write_text(
        page.replace("__DATA__", json.dumps(episodes).replace("</", "<\\/")), encoding="utf-8"
    )
    print(
        json.dumps(
            dict(
                episodes=len(episodes),
                frames=sum(len(e["frames"]) for e in episodes),
                html_bytes=out.stat().st_size,
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--visual", type=Path, required=True)
    p.add_argument("--external", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    build(a.visual, a.external, a.out)
