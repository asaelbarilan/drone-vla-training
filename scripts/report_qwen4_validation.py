"""D-115 exact-image report and verification; never performs inference."""

import base64
import hashlib
import html
import json
from pathlib import Path

from qwen4_validation import OUT, evaluate, read, save

f = read(OUT / "FREEZE.json")
rows = evaluate()
gate = read(OUT / "GATE.json")
cards = []
verified = 0
for c, r in zip(f["cases"], rows, strict=True):
    raw = (OUT / (c["id"] + ".png")).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == c["sha256"]
    assert raw == Path(c["image"]).read_bytes()
    path = OUT / (c["id"] + ".json")
    record = read(path) if path.exists() else {}
    if record:
        b = record["request"]
        assert base64.b64decode(b["messages"][0]["images"][0]) == raw
        assert (
            b["messages"][0]["content"] == f["spec"]["prompt"]
            and b["format"] == f["spec"]["schema"]
        )
        assert b["options"] == f["options"] and b["model"] == f["model"]["name"]
        if "reply" in record:
            assert record["reply"]["model"] == f["model"]["name"] and record["reply"]["done"]
            for resident in record["residency"]["models"]:
                assert resident["digest"] == f["model"]["digest"] and resident["size_vram"] == 0
        verified += 1
    marks = []
    for box, color in [(c["box"], "#36ff92"), (r.get("box_pixels"), "#ffe64a")]:
        if box:
            x, y, x2, y2 = box
            marks.append(
                f'<rect x="{x}" y="{y}" width="{x2 - x}" height="{y2 - y}" fill="none" stroke="{color}" stroke-width="1.5"/>'  # noqa: E501
            )
    uri = "data:image/png;base64," + base64.b64encode(raw).decode()
    a = r.get("answer", {})
    details = json.dumps(a, ensure_ascii=False)
    if "iou" in r:
        details += f" | IoU {r['iou']:.4f}; center on target: {r['center_in_target']}"
    source = f"{c['run']} / {c['call']} / {c['time']:.2f} s"
    full = (
        f["spec"]["prompt"]
        + "\n\n"
        + json.dumps(
            record.get("reply", record.get("error", "Pending")), indent=2, ensure_ascii=False
        )
    )
    cards.append(
        f'<article id="{c["id"]}"><h2>{c["id"].replace("_", " ")} <span class="{r["status"]}">{r["status"].replace("_", " ")}</span></h2><p class="small">{source}</p><svg role="img" aria-label="Exact model input with optional diagnostic overlays" viewBox="0 0 224 224"><image href="{uri}" width="224" height="224"/><g class="diagnostic">{"".join(marks)}</g></svg><p>{html.escape(details)}</p><p class="small">Response channel: {r.get("channel", "—")}</p><details><summary>Exact prompt and raw response</summary><pre>{html.escape(full)}</pre></details></article>'  # noqa: E501
    )
status = (
    (
        "PASS — ready for the conditional flight"
        if gate["passed"]
        else "Gate failed — no flight launched"
    )
    if gate["complete"]
    else "Validation running"
)
page = Path("scripts/templates/qwen4_validation.html").read_text(encoding="utf-8")
Path("reports/debugger/qwen4_validation.html").write_text(
    page.replace("__STATUS__", status)
    .replace("__COUNT__", str(gate["passed_cases"]))
    .replace("__CARDS__", "".join(cards)),
    encoding="utf-8",
)
lines = [
    "# D-115: Qwen3-VL4B new-frame validation",
    "",
    status,
    "",
    f["pass_rule"],
    "",
    f["limitations"],
    "",
    "| Case | Expected | Result | IoU | Center on target |",
    "|---|---|---|---:|---|",
]
for c, r in zip(f["cases"], rows, strict=True):
    iou = f"{r['iou']:.4f}" if "iou" in r else "—"
    lines.append(
        f"| {c['id']} | {'visible' if c['box'] else 'absent'} | {r['status']} | {iou} | {r.get('center_in_target', '—')} |"  # noqa: E501
    )
lines += [
    "",
    "Six new input hashes relative to D-113/D-114. Source bytes and observation IDs checked. Reference boxes visually inspected before inference; none sent to model. CPU-only execution, no cloud calls or retries. Full model digest/options/requests/replies preserved.",  # noqa: E501
    "",
    f"Verified {verified} request identities. Conditional flight permitted: {gate['flight_permitted']}.",  # noqa: E501
]
(OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
save(
    OUT / "VERIFICATION.json",
    dict(
        requests_verified=verified,
        input_images=6,
        source_bytes_exact=True,
        cloud_calls=0,
        gate=gate,
    ),
)
print(json.dumps(gate))
