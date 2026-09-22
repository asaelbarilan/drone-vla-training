"""D155: score a chunk adapter by rollout, against the text-only baseline and blind.

Rollout: stand at step 0, predict the next 8 steps, jump 8 steps forward, look at
the frame actually recorded there, predict again. Summing the predicted steps
gives an endpoint, which is the quantity the baselines in baselines.json measure.

This is NOT closed-loop flight. The frames are the ones the real pilot flew to, so
the model is never shown the consequences of its own drift. A rollout number here
cannot be compared with any published success rate.

Three numbers are always produced together: the model on real frames, the same
model on flat gray frames, and the text-only baseline for that split. Distinct
prediction counts are reported too - a collapsed model can post a fair median.
"""

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import run_smol_frd_overfit as api
import torch
from peft import PeftModel
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/uav_flow_chunks_20260921"
STORE = Path("D:/drone_vla_pilot/data/uav_flow_chunks_20260921")
PROMPT = (
    "Drone forward camera. Task: {instruction} "
    "Predict the next {k} movement steps, in metres and degrees, as {n} numbers: "
    "six per step, x y z then the three rotations."
)
LEADING = re.compile(r"^\s*(?:-?\d+(?:\.\d+)?\s+)*-?\d+(?:\.\d+)?")
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def parse(text, k):
    """Numbers from the start of the output only; needs a full chunk to count."""
    head = LEADING.match(text)
    if not head:
        return None
    values = [float(v) for v in NUMBER.findall(head.group(0))]
    return np.array(values[: 6 * k]).reshape(k, 6) if len(values) >= 6 * k else None


def predict(model, processor, image, instruction, k):
    prompt = PROMPT.format(instruction=instruction, k=k, n=6 * k)
    content = [{"type": "image", "image": image}, {"type": "text", "text": prompt}]
    text = processor.apply_chat_template(
        [{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True
    )
    batch = processor(text=[text], images=[image], return_tensors="pt")
    with torch.inference_mode():
        tokens = model.generate(
            **api.cuda(batch), max_new_tokens=6 * k * 5, do_sample=False, use_cache=True
        )
    raw = processor.tokenizer.decode(
        tokens[0, batch["input_ids"].shape[1] :], skip_special_tokens=True
    )
    return raw, parse(raw, k)


def frame(path, gray):
    picture = Image.open(path).convert("RGB")
    picture.thumbnail((256, 256))
    return Image.new("RGB", picture.size, (127, 127, 127)) if gray else picture


def rollout(model, processor, episodes, by_episode, k, gray):
    errors, details, failed = [], [], 0
    for episode in episodes:
        steps = by_episode[episode["episode"]]
        total = np.zeros(6)
        ok = True
        for anchor in range(0, len(steps), k):
            row = steps[anchor]
            _, chunk = predict(model, processor, frame(row["image"], gray), row["instruction"], k)
            if chunk is None:
                ok = False
                break
            total += chunk[: min(k, len(steps) - anchor)].sum(axis=0)
        if not ok:
            failed += 1
            continue
        truth = np.array(episode["endpoint_m"])
        errors.append(float(np.linalg.norm(total[:3] - truth)))
        details.append(
            dict(
                episode=episode["episode"],
                predicted=[round(float(v), 3) for v in total[:3]],
                truth=[round(float(v), 3) for v in truth],
                error_m=round(errors[-1], 3),
            )
        )
    ordered = sorted(errors)
    distinct = {tuple(d["predicted"]) for d in details}
    return (
        dict(
            episodes=len(episodes),
            scored=len(errors),
            unparsed_episodes=failed,
            distinct_endpoints=len(distinct),
            median_final_error_m=round(ordered[len(ordered) // 2], 3) if ordered else None,
            mean_final_error_m=round(sum(errors) / len(errors), 3) if errors else None,
        ),
        details,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--split", default="split_unseen")
    parser.add_argument("--chunk", type=int, default=8)
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--tag", default="unseen")
    args = parser.parse_args()

    baselines = json.loads((REPORT / "baselines.json").read_text(encoding="utf-8"))[args.split]
    steps = [
        json.loads(s) for s in (STORE / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    episodes = [
        json.loads(s) for s in (STORE / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    by_episode = {}
    for row in steps:
        if row[args.split] == "val":
            by_episode.setdefault(row["episode"], []).append(row)
    for key in by_episode:
        by_episode[key].sort(key=lambda r: r["step"])

    val = sorted((e for e in episodes if e[args.split] == "val"), key=lambda e: e["episode"])[
        : args.episodes
    ]

    processor = api.load_processor()
    model = PeftModel.from_pretrained(api.load_base(), args.adapter)
    model.eval()

    real, real_rows = rollout(model, processor, val, by_episode, args.chunk, False)
    gray, gray_rows = rollout(model, processor, val, by_episode, args.chunk, True)

    bar = baselines["target_to_beat_m"]
    summary = dict(
        adapter=args.adapter,
        split=args.split,
        chunk=args.chunk,
        caveat=(
            "rollout over recorded frames, not closed-loop flight; "
            "not comparable to published success rates"
        ),
        median_trajectory_m=baselines["median_trajectory_m"],
        baselines=dict(
            no_text_m=baselines["no_text"]["median_final_error_m"],
            text_only_m=baselines["text_nearest_neighbour"]["median_final_error_m"],
            bar_m=bar,
        ),
        model=dict(real=real, gray=gray),
        beats_text_only=real["median_final_error_m"] is not None
        and real["median_final_error_m"] < bar,
        vision_helps=real["median_final_error_m"] is not None
        and gray["median_final_error_m"] is not None
        and real["median_final_error_m"] < gray["median_final_error_m"],
    )
    gray_by_episode = {row["episode"]: row["error_m"] for row in gray_rows}
    paired = [
        (row["error_m"], gray_by_episode[row["episode"]])
        for row in real_rows
        if row["episode"] in gray_by_episode
    ]
    if paired:
        wins = sum(a < b for a, b in paired)
        n = sum(a != b for a, b in paired)
        k = min(wins, n - wins)
        summary["vision_sign_test"] = dict(
            better_with_vision=wins,
            comparable_episodes=n,
            p=round(min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n), 4)
            if n
            else 1.0,
        )
    (REPORT / f"scored_{args.tag}.json").write_text(
        json.dumps(dict(summary=summary, real=real_rows, gray=gray_rows), indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
