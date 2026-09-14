"""D-113: six bounded grid/bounding-box calls on frozen sources; no flight."""

import base64
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("reports/localization_formats_20260914")
SOURCE = Path("reports/passage_choice_20260914")


def prepare():
    assert not (OUT / "FREEZE.json").exists(), "Freeze already exists"
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads((SOURCE / "FREEZE.json").read_text(encoding="utf-8"))
    cells = [f"{col}{row}" for row in range(1, 5) for col in "ABCD"]
    grid_prompt = (
        "Locate the red tower in this image. This is a localization test, not navigation. "
        "A neutral 4 by 4 grid is drawn over the image: columns A,B,C,D from left to right; "
        "rows 1,2,3,4 from top to bottom. Each cell is labeled. Return the label of the cell "
        "containing the CENTER of the visible red tower. If no red tower is visible, return "
        "cell=absent. Gray or green structures are not the red tower. Evidence should briefly "
        "describe what is actually visible. Return JSON with evidence and cell."
    )
    box_prompt = (
        "Locate the red tower in this image. This is a localization test, not navigation. "
        "Return visible=true and a tight bounding box around ONLY the visible red tower, "
        "excluding adjacent gray buildings. Box order is [left,top,right,bottom], using a "
        "0..999 grid: (0,0) is the image top-left and (999,999) bottom-right. "
        "If no red tower is visible, return visible=false and box=[0,0,0,0]. Gray or green "
        "structures are not the red tower. Evidence should briefly describe what is actually "
        "visible. Return JSON with evidence, visible and box."
    )
    variants = dict(
        grid=dict(
            prompt=grid_prompt,
            schema=dict(
                type="object",
                properties=dict(
                    evidence=dict(type="string", maxLength=120),
                    cell=dict(type="string", enum=[*cells, "absent"]),
                ),
                required=["evidence", "cell"],
                additionalProperties=False,
            ),
        ),
        bbox=dict(
            prompt=box_prompt,
            schema=dict(
                type="object",
                properties=dict(
                    evidence=dict(type="string", maxLength=120),
                    visible=dict(type="boolean"),
                    box=dict(
                        type="array",
                        items=dict(type="integer", minimum=0, maximum=999),
                        minItems=4,
                        maxItems=4,
                    ),
                ),
                required=["evidence", "visible", "box"],
                additionalProperties=False,
            ),
        ),
    )
    cases = []
    for case in source["cases"]:
        name = case["id"]
        raw = (SOURCE / (name + ".png")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case["source_sha256"]
        (OUT / (name + "_bbox.png")).write_bytes(raw)
        image = Image.open(SOURCE / (name + ".png")).convert("RGB")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 10)
        for x in (56, 112, 168):
            draw.line((x, 0, x, 223), fill=(230, 230, 230), width=1)
        for y in (56, 112, 168):
            draw.line((0, y, 223, y), fill=(230, 230, 230), width=1)
        for row in range(4):
            for col in range(4):
                x, y = col * 56 + 3, row * 56 + 2
                label = f"{'ABCD'[col]}{row + 1}"
                draw.rectangle((x - 1, y, x + 13, y + 12), fill=(15, 20, 25))
                draw.text((x, y), label, font=font, fill=(255, 255, 255))
        image.save(OUT / (name + "_grid.png"))
        cases.append(
            dict(
                id=name,
                source_run=case["run"],
                source_call=case["call"],
                source_t=case["source_t"],
                source_sha256=case["source_sha256"],
                expected_cell="B2" if name == "visible_target" else "absent",
                expected_box_pixels=[77, 72, 85, 98] if name == "visible_target" else None,
                input_sha256={
                    v: hashlib.sha256((OUT / (name + "_" + v + ".png")).read_bytes()).hexdigest()
                    for v in variants
                },
            )
        )
    f = dict(
        cases=cases,
        variants=variants,
        inference=source["inference"],
        calls_budget=6,
        grid_size=4,
        box_pass_iou=0.5,
        box_pass_requires_center_in_target=True,
        notes=(
            "Grid has neutral labels/lines added; bbox uses original RGB. "
            "Tasks are localization-only and differ from D-112 navigation prompt. "
            "Coarse-cell and tight-box scores measure different precision. "
            "No truth annotations sent."
        ),
    )
    (OUT / "FREEZE.json").write_text(json.dumps(f, indent=2), encoding="utf-8")
    print("Prepared three originals and three labeled grids; no model calls")


def evaluate():
    f = json.loads((OUT / "FREEZE.json").read_text(encoding="utf-8"))
    rows = []
    for c in f["cases"]:
        for variant in f["variants"]:
            record = json.loads((OUT / f"{c['id']}_{variant}.json").read_text(encoding="utf-8"))
            r = dict(case=c["id"], variant=variant, passed=False)
            try:
                answer = json.loads(record["reply"]["message"]["content"])
                r["answer"] = answer
                if variant == "grid":
                    assert set(answer) == {"evidence", "cell"}
                    assert (
                        answer["cell"]
                        in f["variants"][variant]["schema"]["properties"]["cell"]["enum"]
                    )
                    r.update(valid=True, passed=answer["cell"] == c["expected_cell"])
                else:
                    assert (
                        set(answer) == {"evidence", "visible", "box"}
                        and type(answer["visible"]) is bool
                    )
                    box = answer["box"]
                    assert len(box) == 4 and all(type(x) is int and 0 <= x <= 999 for x in box)
                    if not answer["visible"]:
                        assert box == [0, 0, 0, 0]
                        r.update(valid=True, passed=c["expected_box_pixels"] is None)
                    else:
                        assert box[0] < box[2] and box[1] < box[3]
                        b = [x * 223 / 999 for x in box]
                        r.update(valid=True, box_pixels=b)
                        target = c["expected_box_pixels"]
                        if target:
                            inter = max(0, min(b[2], target[2]) - max(b[0], target[0])) * max(
                                0, min(b[3], target[3]) - max(b[1], target[1])
                            )
                            union = (
                                (b[2] - b[0]) * (b[3] - b[1])
                                + (target[2] - target[0]) * (target[3] - target[1])
                                - inter
                            )
                            iou = inter / union
                            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                            inside = target[0] <= cx <= target[2] and target[1] <= cy <= target[3]
                            r.update(
                                iou=iou,
                                center_in_target=inside,
                                passed=iou >= f["box_pass_iou"] and inside,
                            )
            except Exception as exc:
                r.update(valid=False, error=str(exc))
            rows.append(r)
    (OUT / "RESULTS.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2))


def run():
    f = json.loads((OUT / "FREEZE.json").read_text(encoding="utf-8"))
    p = f["inference"]
    assert not any(
        (OUT / f"{c['id']}_{v}.json").exists() for c in f["cases"] for v in f["variants"]
    ), "Refuse repeated calls; use evaluate"
    with urllib.request.urlopen(p["host"] + "/api/tags", timeout=10) as response:
        tags = json.load(response)
    assert (
        next(t for t in tags["models"] if t["name"] == p["model_id"])["digest"]
        == p["expected_digest"]
    )
    for c in f["cases"]:
        for variant, spec in f["variants"].items():
            raw = (OUT / f"{c['id']}_{variant}.png").read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            assert digest == c["input_sha256"][variant]
            body = dict(
                model=p["model_id"],
                messages=[
                    dict(
                        role="user", content=spec["prompt"], images=[base64.b64encode(raw).decode()]
                    )
                ],
                stream=False,
                think=p["think"],
                keep_alive=p["keep_alive"],
                options=dict(
                    temperature=p["temperature"],
                    seed=p["sampling_seed"],
                    num_ctx=p["num_ctx"],
                    num_predict=p["num_predict"],
                ),
                format=spec["schema"],
            )
            req = urllib.request.Request(
                p["host"] + "/api/chat",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=180) as response:
                reply = json.load(response)
            record = dict(
                case=c["id"],
                variant=variant,
                input_sha256=digest,
                prompt=spec["prompt"],
                schema=spec["schema"],
                options=body["options"],
                reply=reply,
            )
            (OUT / f"{c['id']}_{variant}.json").write_text(
                json.dumps(record, indent=2), encoding="utf-8"
            )
            print(c["id"], variant, reply["message"]["content"], flush=True)
    evaluate()


if __name__ == "__main__":
    {"prepare": prepare, "run": run, "evaluate": evaluate}[sys.argv[1]]()
