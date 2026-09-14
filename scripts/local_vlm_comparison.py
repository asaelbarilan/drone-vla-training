"""D-114: bounded installed-model replay of D-113; no flight or cloud calls."""

import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import jsonschema

SOURCE = Path("reports/localization_formats_20260914")
OUT = Path("reports/local_vlm_comparison_20260914")
HOST = "http://127.0.0.1:11435"
MODELS = [
    "moondream:latest",
    "richardyoung/smolvlm2-2.2b-instruct:Q4_K_M",
    "qwen3-vl:2b",
    "qwen3-vl:4b",
    "qwen3-vl:8b",
    "qwen3.5:2b",
    "qwen3.5:4b",
]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def api(host, path, body=None, timeout=15):
    req = urllib.request.Request(
        host + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def prepare():
    assert not (OUT / "FREEZE.json").exists(), "Existing freeze must not be overwritten"
    OUT.mkdir(parents=True, exist_ok=True)
    source = read(SOURCE / "FREEZE.json")
    tags = api("http://127.0.0.1:11434", "/api/tags")["models"]
    models = []
    for index, name in enumerate(MODELS):
        tag = next(t for t in tags if t["name"] == name)
        metadata = api("http://127.0.0.1:11434", "/api/show", {"model": name})
        models.append(
            dict(
                id=f"m{index + 1}",
                name=name,
                digest=tag["digest"],
                size=tag["size"],
                capabilities=metadata.get("capabilities", []),
            )
        )
        save(OUT / f"m{index + 1}_metadata.json", metadata)
    for case in source["cases"]:
        for variant in source["variants"]:
            raw = (SOURCE / f"{case['id']}_{variant}.png").read_bytes()
            assert hashlib.sha256(raw).hexdigest() == case["input_sha256"][variant]
            (OUT / f"{case['id']}_{variant}.png").write_bytes(raw)
    freeze = dict(
        decision="D-114",
        models=models,
        cases=source["cases"],
        variants=source["variants"],
        source_freeze_sha256=hashlib.sha256((SOURCE / "FREEZE.json").read_bytes()).hexdigest(),
        host=HOST,
        max_inference_attempts=42,
        timeout_s=300,
        options=dict(temperature=0, seed=0, num_ctx=8192, num_predict=192, num_gpu=0, num_thread=4),
        keep_alive="10m",
        box_pass_iou=0.5,
        parser="Whole JSON (optional enclosing markdown fence); content then thinking. "
        "First schema-valid answer wins; both channels preserved. No coordinate repair.",
        interpretation="Identical D-113 prompts and schemas, including 0..999 box convention. "
        "This tests the installed model/backend/shared interface, not best native "
        "model performance. CPU-only isolated server; latency not a flight benchmark. "
        "Gemma is a reused historical baseline. Three scenes, one positive only.",
        errors="No retries. HTTP/runtime errors recorded separately from valid wrong answers. "
        "Request timeout stops remaining calls for that model to avoid overlapping work.",
    )
    save(OUT / "FREEZE.json", freeze)
    print("Frozen 7 models, 42 calls, identical sources/prompts. No inference.")


def parse(reply, spec):
    errors = []
    for channel in ("content", "thinking"):
        text = reply.get("message", {}).get(channel, "").strip()
        if not text:
            continue
        if text.startswith("```") and text.endswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            answer = json.loads(text)
            jsonschema.validate(answer, spec["schema"])
            return answer, channel
        except (ValueError, jsonschema.ValidationError) as exc:
            errors.append(f"{channel}: {str(exc)[:200]}")
    raise ValueError("; ".join(errors) or "No answer in either channel")


def score(answer, case, variant):
    result = dict(passed=False)
    if variant == "grid":
        result.update(
            passed=answer["cell"] == case["expected_cell"],
            presence_correct=(answer["cell"] != "absent")
            == (case["expected_box_pixels"] is not None),
        )
    else:
        target = case["expected_box_pixels"]
        result["presence_correct"] = answer["visible"] == (target is not None)
        if not answer["visible"]:
            if answer["box"] != [0, 0, 0, 0]:
                raise ValueError("Absent answer must use zero box")
            result["passed"] = target is None
        else:
            b = [x * 223 / 999 for x in answer["box"]]
            if not (b[0] < b[2] and b[1] < b[3]):
                raise ValueError("Box has nonpositive area")
            result["box_pixels"] = b
            if target:
                inter = max(0, min(b[2], target[2]) - max(b[0], target[0])) * max(
                    0, min(b[3], target[3]) - max(b[1], target[1])
                )
                union = (
                    (b[2] - b[0]) * (b[3] - b[1])
                    + (target[2] - target[0]) * (target[3] - target[1])
                    - inter
                )
                cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                inside = target[0] <= cx < target[2] and target[1] <= cy < target[3]
                result.update(
                    iou=inter / union,
                    center_in_target=inside,
                    passed=inter / union >= 0.5 and inside,
                )
    return result


def evaluate():
    f = read(OUT / "FREEZE.json")
    rows = []
    for model in [dict(id="gemma", name="gemma4:e2b (saved baseline)"), *f["models"]]:
        for case in f["cases"]:
            for variant, spec in f["variants"].items():
                filename = f"{case['id']}_{variant}.json"
                path = SOURCE / filename if model["id"] == "gemma" else OUT / model["id"] / filename
                row = dict(
                    model=model["id"],
                    name=model["name"],
                    case=case["id"],
                    variant=variant,
                    passed=False,
                    status="pending",
                )
                if path.exists():
                    record = read(path)
                    row["seconds"] = record.get("seconds")
                    if record.get("error"):
                        row.update(status="runtime_error", error=record["error"])
                    else:
                        try:
                            answer, channel = parse(record["reply"], spec)
                            row.update(answer=answer, channel=channel)
                            row.update(score(answer, case, variant))
                            row["status"] = "pass" if row["passed"] else "wrong_answer"
                        except (ValueError, KeyError) as exc:
                            row.update(status="invalid_output", error=str(exc))
                rows.append(row)
    save(OUT / "RESULTS.json", rows)
    return rows


def run():
    f = read(OUT / "FREEZE.json")
    tags = api(HOST, "/api/tags")["models"]
    # Resuming only skips durable attempts; never repeat a completed or uncertain request.
    for model in f["models"]:
        assert next(t for t in tags if t["name"] == model["name"])["digest"] == model["digest"]
        directory = OUT / model["id"]
        directory.mkdir(exist_ok=True)
        if (directory / "STOP.json").exists():
            continue
        try:
            for case in f["cases"]:
                for variant, spec in f["variants"].items():
                    path = directory / f"{case['id']}_{variant}.json"
                    if path.exists():
                        continue
                    marker = path.with_suffix(".attempt.json")
                    assert not marker.exists(), (
                        "Uncertain prior attempt; never repeat automatically"
                    )
                    raw = (OUT / f"{case['id']}_{variant}.png").read_bytes()
                    digest = hashlib.sha256(raw).hexdigest()
                    assert digest == case["input_sha256"][variant]
                    body = dict(
                        model=model["name"],
                        messages=[
                            dict(
                                role="user",
                                content=spec["prompt"],
                                images=[base64.b64encode(raw).decode()],
                            )
                        ],
                        stream=False,
                        keep_alive=f["keep_alive"],
                        options=f["options"],
                        format=spec["schema"],
                    )
                    if "thinking" in model["capabilities"]:
                        body["think"] = False
                    record = dict(
                        model=model,
                        case=case["id"],
                        variant=variant,
                        input_sha256=digest,
                        request=body,
                    )
                    save(marker, dict(started=time.time(), input_sha256=digest))
                    start = time.monotonic()
                    print(f"START {model['name']} {case['id']} {variant}", flush=True)
                    try:
                        record["reply"] = api(HOST, "/api/chat", body, timeout=f["timeout_s"])
                        record["residency"] = api(HOST, "/api/ps")
                        assert all(
                            m.get("size_vram", 0) == 0 for m in record["residency"]["models"]
                        )
                    except urllib.error.HTTPError as exc:
                        record["error"] = f"HTTP {exc.code}: {exc.read().decode(errors='replace')}"
                    except Exception as exc:
                        record["error"] = f"{type(exc).__name__}: {exc}"
                        save(directory / "STOP.json", dict(reason=record["error"]))
                    record["seconds"] = time.monotonic() - start
                    save(path, record)
                    rows = evaluate()
                    row = next(
                        r
                        for r in rows
                        if r["model"] == model["id"]
                        and r["case"] == case["id"]
                        and r["variant"] == variant
                    )
                    print(json.dumps(row), flush=True)
                    if (directory / "STOP.json").exists():
                        break
                if (directory / "STOP.json").exists():
                    break
        finally:
            # Unload only on our isolated server. This is not an inference request.
            try:
                save(
                    directory / "UNLOAD.json",
                    api(HOST, "/api/generate", dict(model=model["name"], keep_alive=0), timeout=30),
                )
            except Exception as exc:
                save(directory / "UNLOAD.json", dict(error=str(exc)))
                raise
    evaluate()


if __name__ == "__main__":
    {"prepare": prepare, "run": run, "evaluate": evaluate}[sys.argv[1]]()
