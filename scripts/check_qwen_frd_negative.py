"""Reject modified image/control copies without touching original model runs."""

import argparse
import asyncio
import json
import shutil
import sys
import traceback
from pathlib import Path

sys.path.insert(0, "scripts")
from audit_qwen_frd_pair import audit

parser = argparse.ArgumentParser()
parser.add_argument("--runs", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
root = args.runs
report = []
for kind in ("image", "control"):
    out = args.out / kind
    shutil.copytree(root, out, ignore=shutil.ignore_patterns("*.html"))
    folder = out / "qwen_frd_trained_s1400"
    if kind == "image":
        path = folder / "images/00000_mosaic.png"
        path.write_bytes(path.read_bytes() + b"tamper")
    else:
        path = folder / "events.jsonl"
        events = [json.loads(x) for x in path.read_text().splitlines()]
        event = next(e for e in events if e["event_type"] == "control")
        event["payload"]["command"]["velocity"]["x"] += 0.25
        path.write_text("".join(json.dumps(e) + "\n" for e in events))
    try:
        asyncio.run(audit(out))
    except AssertionError as exc:
        line = traceback.extract_tb(exc.__traceback__)[-1].line
        expected = (
            "image_bytes(mosaic) == original"
            if kind == "image"
            else "expected.velocity == actual.velocity"
        )
        assert expected in line, (line, expected)
        report.append(dict(mutation=kind, rejected=True, check=line))
    else:
        raise AssertionError("tampering was accepted")
(args.out / "negative_audit.json").write_text(json.dumps(report, indent=2))
print(report)
