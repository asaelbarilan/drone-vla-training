"""D-115: six new saved frames; frozen all-case gate before one conditional flight."""

import base64
import hashlib
import json
import sys
import time
from pathlib import Path

from local_vlm_comparison import api, parse, read, save, score

OUT = Path("reports/qwen4_validation_20260915")
HOST = "http://127.0.0.1:11435"


def prepare():
    assert not (OUT / "FREEZE.json").exists()
    source = read(Path("reports/local_vlm_comparison_20260914/FREEZE.json"))
    model = next(m for m in source["models"] if m["name"] == "qwen3-vl:4b")
    tags = api("http://127.0.0.1:11434", "/api/tags")["models"]
    assert next(t for t in tags if t["name"] == model["name"])["digest"] == model["digest"]
    cases = read(OUT / "SELECTION.json")
    prior_hashes = {c["input_sha256"][v] for c in source["cases"] for v in source["variants"]}
    assert len(cases) == 6 and len({c["sha256"] for c in cases}) == 6
    for c in cases:
        raw = (OUT / (c["id"] + ".png")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == c["sha256"]
        assert raw == Path(c["image"]).read_bytes() and c["sha256"] not in prior_hashes
        call = read(Path("runs") / c["run"] / "debug/calls" / (c["call"] + ".json"))
        assert call["observation_seq"] == c["seq"]
        c["expected_box_pixels"] = c["box"]
    save(
        OUT / "FREEZE.json",
        dict(
            decision="D-115",
            model=model,
            cases=cases,
            spec=source["variants"]["bbox"],
            options=source["options"],
            think=False,
            max_attempts=6,
            host=HOST,
            timeout_s=300,
            keep_alive="10m",
            pass_rule=(
                "All 6 pass. Each positive: IoU>=0.5 and center inside reference. Each "
                "negative: visible=false and zero box. No retries or prompt changes."
            ),
            selection=(
                "Selected using image content only, before inference; original source RGB "
                "bytes, no crops or labels. Three positives: far-left small, mid-center, near "
                "clipped. Three negatives: two different clutter seeds and an empty view "
                "after turning. Reference boxes are offline red-body bounds confirmed by "
                "visual inspection; never included in model request."
            ),
            limitations=(
                "Six new image hashes relative to D-113/D-114, not six independent worlds. "
                "Two positive frames share one hover flight, and one positive comes from the "
                "earlier clutter seed. This is a small diagnostic gate, not a planning or "
                "generalization benchmark."
            ),
            conditional_flight=(
                "Only if all six pass: named Qwen3-VL4B variant of current C5 clutter "
                "pipeline, one seed1061 flight, exact evidence and debugger inspection. No "
                "automatic extra flights."
            ),
        ),
    )
    print("Frozen six new images and all-case acceptance gate; no inference")


def evaluate():
    f = read(OUT / "FREEZE.json")
    rows = []
    for c in f["cases"]:
        row = dict(case=c["id"], passed=False, status="pending")
        path = OUT / (c["id"] + ".json")
        if path.exists():
            record = read(path)
            if record.get("error"):
                row.update(status="runtime_error", error=record["error"])
            else:
                try:
                    answer, channel = parse(record["reply"], f["spec"])
                    row.update(answer=answer, channel=channel)
                    row.update(score(answer, c, "bbox"))
                    row["status"] = "pass" if row["passed"] else "wrong_answer"
                except ValueError as e:
                    row.update(status="invalid_output", error=str(e))
        rows.append(row)
    save(OUT / "RESULTS.json", rows)
    save(
        OUT / "GATE.json",
        dict(
            complete=all(r["status"] != "pending" for r in rows),
            passed=all(r["passed"] for r in rows),
            passed_cases=sum(r["passed"] for r in rows),
            required=6,
            flight_permitted=all(r["passed"] for r in rows),
        ),
    )
    return rows


def run():
    f = read(OUT / "FREEZE.json")
    assert (
        next(t for t in api(HOST, "/api/tags")["models"] if t["name"] == f["model"]["name"])[
            "digest"
        ]
        == f["model"]["digest"]
    )
    try:
        for c in f["cases"]:
            path = OUT / (c["id"] + ".json")
            marker = OUT / (c["id"] + ".attempt.json")
            if path.exists():
                continue
            assert not marker.exists(), "Refuse uncertain repeated attempt"
            raw = (OUT / (c["id"] + ".png")).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == c["sha256"]
            body = dict(
                model=f["model"]["name"],
                messages=[
                    dict(
                        role="user",
                        content=f["spec"]["prompt"],
                        images=[base64.b64encode(raw).decode()],
                    )
                ],
                stream=False,
                think=False,
                format=f["spec"]["schema"],
                options=f["options"],
                keep_alive=f["keep_alive"],
            )
            record = dict(case=c["id"], input_sha256=c["sha256"], request=body)
            save(marker, dict(started=time.time(), input_sha256=c["sha256"]))
            start = time.monotonic()
            print("START", c["id"], flush=True)
            try:
                record["reply"] = api(HOST, "/api/chat", body, timeout=f["timeout_s"])
                record["residency"] = api(HOST, "/api/ps")
            except Exception as e:
                record["error"] = f"{type(e).__name__}: {e}"
            record["seconds"] = time.monotonic() - start
            save(path, record)
            rows = evaluate()
            print(json.dumps(next(r for r in rows if r["case"] == c["id"])), flush=True)
            if record.get("error"):
                break
    finally:
        save(
            OUT / "UNLOAD.json",
            api(HOST, "/api/generate", dict(model=f["model"]["name"], keep_alive=0), timeout=30),
        )
    print(json.dumps(read(OUT / "GATE.json")), flush=True)


if __name__ == "__main__":
    {"prepare": prepare, "run": run, "evaluate": evaluate}[sys.argv[1]]()
