"""Exactly three local saved-RGB attribute-contract probes; no automatic retries."""

import base64
import hashlib
import json
import urllib.request
from pathlib import Path
from uavlab.plugins.reasoning.onfly import OnFlyDecisionAgent

ROOT = Path("runs/c5_clutter_stable_20260914_s1061")
OUT = Path("reports/clutter_stable_20260914/attribute_probe")
OUT.mkdir(exist_ok=True)
m = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
p = m["architecture_config"]["inference"]["params"]
with urllib.request.urlopen(p["host"] + "/api/tags", timeout=10) as r:
    tags = json.load(r)
assert (
    next(t for t in tags["models"] if t["name"] == p["model_id"])["digest"] == p["expected_digest"]
)
params = dict(m["architecture_config"]["policy"]["params"], semantic_color_guard=True)
policy = OnFlyDecisionAgent(**params)
rows = []
for name in ("call-000004", "call-000022", "call-000045"):
    c = json.loads((ROOT / "debug/calls" / (name + ".json")).read_text(encoding="utf-8"))
    prompt = c["prompt"] + (
        " Report observed_color for the object at u,v from its actual appearance, "
        "even if it differs from the requested color. In evidence describe THAT "
        "object only. Also supply explore_u,explore_v at an open passage near "
        "flight height as an alternative if this object does not match. "
        "The alternative must avoid the object's face and reveal more terrain."
    )
    img = (ROOT / c["image_files"][0]).read_bytes()
    body = dict(
        model=p["model_id"],
        messages=[dict(role="user", content=prompt, images=[base64.b64encode(img).decode()])],
        stream=False,
        think=p["think"],
        keep_alive=p["keep_alive"],
        options=dict(
            temperature=p["temperature"],
            seed=p["sampling_seed"],
            num_ctx=p["num_ctx"],
            num_predict=p["num_predict"],
        ),
        format=policy._schema(224, 224),
    )
    req = urllib.request.Request(
        p["host"] + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        reply = json.load(r)
    answer = json.loads(reply["message"]["content"])
    row = dict(
        source_call=name,
        source_image=str(ROOT / c["image_files"][0]),
        source_sha256=hashlib.sha256(img).hexdigest(),
        prompt=prompt,
        schema=body["format"],
        options=body["options"],
        raw_reply=reply,
        answer=answer,
        effective_kind="target"
        if answer["kind"] == "target" and answer["observed_color"] == "red"
        else "exploration",
    )
    rows.append(row)
    (OUT / (name + ".json")).write_text(json.dumps(row, indent=2), encoding="utf-8")
    print(name, answer, "=>", row["effective_kind"], flush=True)
(OUT / "SUMMARY.json").write_text(
    json.dumps(
        dict(
            completed_calls=len(rows),
            cloud_calls=0,
            all_mismatches_rejected=all(r["effective_kind"] == "exploration" for r in rows),
            scope="Selected negative frames only; does not prove passage quality or navigation",
        ),
        indent=2,
    ),
    encoding="utf-8",
)
