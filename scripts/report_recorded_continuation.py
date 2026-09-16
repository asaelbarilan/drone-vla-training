"""Archive and visually export the bounded continuation, without inference."""

import asyncio
import gzip
import json
import math
import shutil
from collections import Counter
from pathlib import Path

from audit_clutter_stable import audit

from uavlab.analysis.flight_debugger import _sources, html_document, load_run

OUT = Path("reports/continuation_20260916")
NAME = "c5_commitment_continued_20260916_s1061"
SOURCE = "c5_target_commitment_20260915_s1061"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


async def main():
    root = Path("runs") / NAME
    live = read(root / "CONTINUATION_AUDIT.json")
    assert live["passed"] and live["matched"]["control"] == 1800
    result = read(root / "result.json")
    calls = [read(p) for p in sorted((root / "debug/calls").glob("*.json"))]
    cached = calls[:134]
    fresh = calls[134:]
    assert all(c["cache_hit"] and c["status"] == "complete" for c in cached)
    assert len(fresh) == live["fresh_requests"] <= 47
    data = [await load_run(Path("runs") / n) for n in [SOURCE, NAME]]
    original, continuation = data
    for a, b in zip(original["frames"], continuation["frames"], strict=False):
        if a["t"] > 90:
            break
        for field in ["t", "position", "velocity", "yaw", "distance"]:
            assert a[field] == b[field], (field, a["t"])
    frames = continuation["frames"]
    final = frames[-1]
    selected = [
        min(frames, key=lambda f: abs(f["t"] - t))
        for t in [90, 92, 94, 96, 98, 100, 105, 110, 115, 120]
    ]
    proof = await audit(NAME)
    proof.update(
        result=result,
        prefix=live["matched"],
        cached_completed=len(cached),
        fresh_calls=dict(Counter(c["status"] for c in fresh)),
        fresh_requested=len(fresh),
        fresh_completed_latency_s=[
            c["latency_ns"] / 1e9 for c in fresh if c["status"] == "complete"
        ],
        closest_m=min(f["distance"] for f in frames),
        final_speed_mps=math.sqrt(sum(v * v for v in final["velocity"])),
        final_frame={k: v for k, v in final.items() if k != "rgb"},
        samples=[{k: f[k] for k in ["t", "distance", "velocity", "position"]} for f in selected],
        note="Original90s timeout is preserved. Cached prefix is not new inference; "
        "success here uses a120s time budget. Terminal declaration does not "
        "by itself establish physically settled hover.",
    )
    (OUT / "AUDIT.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    banner = (
        '<div style="padding:12px 24px;background:#18303d;color:#e3f5ff">'
        "D-122 continuation: original 90 s timeout preserved. The first 90 s "
        "reconstruct recorded decisions; fresh local inference continues for up "
        "to 30 s. Cached-prefix latency is not new model compute.</div>"
    )
    page = html_document(dict(schema=1, runs=data, sources=_sources()))
    page = page.replace("<body>", "<body>" + banner, 1)
    Path("reports/debugger/commitment_continuation.html").write_text(page, encoding="utf-8")
    for filename in ["manifest.json", "result.json", "CONTINUATION_AUDIT.json"]:
        shutil.copy2(root / filename, OUT / filename)
    (OUT / "events.jsonl.gz").write_bytes(
        gzip.compress((root / "events.jsonl").read_bytes(), mtime=0)
    )
    shutil.copytree(root / "debug", OUT / "debug", dirs_exist_ok=True)
    print(
        json.dumps(
            {
                k: proof[k]
                for k in [
                    "poses_matched",
                    "source_images_matched",
                    "fresh_calls",
                    "fresh_requested",
                    "closest_m",
                    "final_speed_mps",
                    "samples",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
