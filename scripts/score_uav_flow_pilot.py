"""D153: score a saved UAV-Flow endpoint adapter against the frozen baselines.

The training run's own parser demanded exactly three numbers. The model emits a
fourth because no end-of-sequence token was ever trained, so every prediction was
discarded as unparsed. This rescoring anchors the match to the start of the
output and takes the first three numbers; prose is still rejected, which was the
reason the strict parser existed.

Alongside the error it reports how many distinct answers the model produced. A
model that has collapsed onto one constant can still post a respectable median,
and that number would mean nothing.
"""

import argparse
import json
import math
import re
from pathlib import Path

import run_smol_frd_overfit as api
import torch
from peft import PeftModel
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/uav_flow_pilot_20260921"
STORE = Path("D:/drone_vla_pilot/data/uav_flow_pilot_20260921")
PROMPT = (
    "Drone forward camera, first frame of the flight. "
    "Task: {instruction} "
    "Predict the final displacement from this position, in metres, "
    "as three numbers x y z in the starting frame."
)
LEADING = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\b")


def parse(text):
    """First three numbers, but only if the output begins with them."""
    found = LEADING.match(text)
    return [float(v) for v in found.groups()] if found else None


def run(model, processor, rows, gray):
    predictions, errors, unparsed = [], [], 0
    for row in rows:
        picture = Image.open(row["image"]).convert("RGB")
        picture.thumbnail((256, 256))
        if gray:
            picture = Image.new("RGB", picture.size, (127, 127, 127))
        content = [
            {"type": "image", "image": picture},
            {"type": "text", "text": PROMPT.format(instruction=row["instruction"])},
        ]
        text = processor.apply_chat_template(
            [{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True
        )
        batch = processor(text=[text], images=[picture], return_tensors="pt")
        with torch.inference_mode():
            tokens = model.generate(
                **api.cuda(batch), max_new_tokens=16, do_sample=False, use_cache=True
            )
        raw = processor.tokenizer.decode(
            tokens[0, batch["input_ids"].shape[1] :], skip_special_tokens=True
        )
        guess = parse(raw)
        predictions.append(dict(id=row["id"], raw=raw, parsed=guess, truth=row["endpoint_m"]))
        if guess is None:
            unparsed += 1
            continue
        errors.append(math.dist(guess, row["endpoint_m"]))
    ordered = sorted(errors)
    rounded = {tuple(round(v, 1) for v in p["parsed"]) for p in predictions if p["parsed"]}
    return (
        dict(
            n=len(rows),
            parsed=len(errors),
            unparsed=unparsed,
            distinct_predictions=len(rounded),
            median_final_error_m=round(ordered[len(ordered) // 2], 3) if ordered else None,
            mean_final_error_m=round(sum(errors) / len(errors), 3) if errors else None,
        ),
        predictions,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adapter", default="D:/drone_vla_pilot/runs/uav_flow_pilot_20260921_a/adapter_s400"
    )
    parser.add_argument("--tag", default="s400")
    args = parser.parse_args()

    manifest = json.loads((REPORT / "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(s) for s in (STORE / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    val = [r for r in rows if r["split"] == "val"]

    processor = api.load_processor()
    model = PeftModel.from_pretrained(api.load_base(), args.adapter)
    model.eval()

    real, real_rows = run(model, processor, val, False)
    gray, gray_rows = run(model, processor, val, True)

    base = manifest["baseline"]
    summary = dict(
        adapter=args.adapter,
        task=manifest["task"],
        val_episodes=len(val),
        median_trajectory_m=base["median_trajectory_m"],
        baselines=dict(
            no_text_m=base["global_no_text"]["median_final_error_m"],
            text_only_m=base["target_to_beat_m"],
        ),
        model=dict(real=real, gray=gray),
        beats_text_only=(
            real["median_final_error_m"] is not None
            and real["median_final_error_m"] < base["target_to_beat_m"]
        ),
    )
    (REPORT / f"scored_{args.tag}.json").write_text(
        json.dumps(dict(summary=summary, real=real_rows, gray=gray_rows), indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
