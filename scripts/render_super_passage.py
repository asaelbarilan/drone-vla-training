"""Export the completed D-96 trace as a portable, interactive visual replay."""

from __future__ import annotations

import base64
import json
from pathlib import Path


def main():
    out = Path("reports/super_passage_probe_20260912")
    data = json.loads((out / "trace.json").read_text(encoding="utf-8"))
    data["frames"] = []
    frame_index = 0
    camera_sample_index = 0
    for sample_index, sample in enumerate(data["samples"]):
        if "camera_file" in sample:
            frame_index = len(data["frames"])
            camera_sample_index = sample_index
            raw = (out / sample["camera_file"]).read_bytes()
            data["frames"].append("data:image/png;base64," + base64.b64encode(raw).decode("ascii"))
        sample["camera_index"] = frame_index
        sample["camera_sample_index"] = camera_sample_index
    manual = json.loads(
        Path("reports/passage_probe_20260912/opening.json").read_text(encoding="utf-8")
    )
    data["manual_route"] = [s["position"] for s in manual["samples"]]
    template = Path("scripts/super_passage_template.html").read_text(encoding="utf-8")
    html = template.replace(
        "__DATA__", json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")
    )
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".gitignore").write_text("camera/\n", encoding="utf-8")
    preview = Path("reports/debugger/super_passage_4160.html")
    preview.write_text(html, encoding="utf-8")
    print(f"Wrote {len(data['frames'])} camera frames and {len(data['plans'])} planner snapshots")
    print(f"Portable HTML: {len(html):,} characters; preview: {preview}")


if __name__ == "__main__":
    main()
