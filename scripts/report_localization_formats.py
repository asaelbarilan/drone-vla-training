"""Rebuild D-113 exact-input localization comparison without inference."""

import base64
import hashlib
import html
import json
from pathlib import Path

OUT = Path("reports/localization_formats_20260914")
f = json.loads((OUT / "FREEZE.json").read_text(encoding="utf-8"))
rows = json.loads((OUT / "RESULTS.json").read_text(encoding="utf-8"))
sections = []
records = []
for case in f["cases"]:
    cards = []
    for variant in f["variants"]:
        raw = (OUT / f"{case['id']}_{variant}.png").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest == case["input_sha256"][variant]
        if variant == "bbox":
            assert digest == case["source_sha256"]
        record = json.loads((OUT / f"{case['id']}_{variant}.json").read_text(encoding="utf-8"))
        records.append(record)
        assert record["input_sha256"] == digest
        assert record["prompt"] == f["variants"][variant]["prompt"]
        assert record["schema"] == f["variants"][variant]["schema"]
        result = next(r for r in rows if r["case"] == case["id"] and r["variant"] == variant)
        assert result["valid"]
        answer = result["answer"]
        marks = []
        detail = ""
        if case["expected_box_pixels"]:
            x, y, right, bottom = case["expected_box_pixels"]
            marks.append(
                f'<rect x="{x}" y="{y}" width="{right - x}" height="{bottom - y}" fill="none" stroke="#36ff92" stroke-width="1"/>'  # noqa: E501
            )
        if variant == "grid":
            label = answer["cell"]
            detail = f"Selected: {label}. Expected: {case['expected_cell']}."
            if label != "absent":
                x = (ord(label[0]) - 65) * 56
                y = (int(label[1]) - 1) * 56
                marks.append(
                    f'<rect x="{x + 1}" y="{y + 1}" width="54" height="54" fill="none" stroke="#ffe64a" stroke-width="2"/>'  # noqa: E501
                )
        else:
            detail = f"Visible: {answer['visible']}. Box: {answer['box']}."
            if answer["visible"]:
                x, y, right, bottom = result["box_pixels"]
                marks.append(
                    f'<rect x="{x}" y="{y}" width="{right - x}" height="{bottom - y}" fill="none" stroke="#ffe64a" stroke-width="1.5"/>'  # noqa: E501
                )
                detail += f" IoU: {result.get('iou', 0):.3f}; box center on target: {result.get('center_in_target', False)}."  # noqa: E501
        uri = "data:image/png;base64," + base64.b64encode(raw).decode()
        title = "Labeled 4 x 4 grid" if variant == "grid" else "Bounding box — original image"
        verdict = "PASS" if result["passed"] else "FAIL"
        cards.append(
            f'<article><h3>{title} <span class="{verdict.lower()}">{verdict}</span></h3><svg viewBox="0 0 224 224" role="img" aria-label="Exact model input with optional diagnostic overlay"><image href="{uri}" width="224" height="224"/><g class="diagnostic">{"".join(marks)}</g></svg><p>{html.escape(detail)}</p><p>{html.escape(answer["evidence"])}</p><details><summary>Exact prompt and response</summary><pre>{html.escape(record["prompt"])}\n\nRESPONSE\n{html.escape(record["reply"]["message"]["content"])}</pre></details></article>'  # noqa: E501
        )
    sections.append(
        f'<section id="{case["id"]}"><h2>{case["id"].replace("_", " ")}</h2><p class="small">{case["source_run"]} · {case["source_call"]} · {case["source_t"]:.2f} s</p><div class="pair">{"".join(cards)}</div></section>'  # noqa: E501
    )
assert len(records) == 6 and all(r["options"] == records[0]["options"] for r in records)
proof = dict(
    completed_calls=6,
    cloud_calls=0,
    flights=0,
    raw_inputs_verified=6,
    original_bbox_inputs_unchanged=3,
    identical_model_options=True,
    grid_correct_cases=sum(r["passed"] for r in rows if r["variant"] == "grid"),
    bbox_correct_cases=sum(r["passed"] for r in rows if r["variant"] == "bbox"),
    bbox_visible_iou=next(
        r["iou"] for r in rows if r["case"] == "visible_target" and r["variant"] == "bbox"
    ),
    runtime_changed=False,
    promoted=False,
)
(OUT / "VERIFICATION.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
template = Path("scripts/templates/localization_formats.html").read_text(encoding="utf-8")
Path("reports/debugger/localization_formats.html").write_text(
    template.replace("__SECTIONS__", "".join(sections)), encoding="utf-8"
)
print(json.dumps(proof, indent=2))
