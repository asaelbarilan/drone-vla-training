"""D159: can the VLM see the instruction's target at the resolution we train on?

Every frame in our stores is a 256 px thumbnail, and the trainer shrinks again to
256. If the target is unreadable at that size the VLA has nothing to learn from
the image, which would explain the identical actions on real, gray and swapped
frames (D157/D155 scoring).

The probe needs no trained model. For each held-out flight the base VLM is asked
which side of the frame the instruction's target is on, at several resolutions,
on the original frame and on its left-right mirror. Mirroring flips the true
answer, so a model that sees the target must answer the opposite; a model that is
guessing answers the same. No ground-truth labels are needed.

Full-resolution frames come from the shard, not from our thumbnail store.
"""

import argparse
import io
import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
import torch
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vlm_resolution_probe_20260923"
QUESTION = (
    'This is a photo from a drone\'s forward camera. A pilot was told: "{instruction}".\n'
    "Is the target of that instruction in the left half or the right half of the photo?\n"
    "Answer with one word: left or right."
)


def episodes(store, subset, count):
    rows = [
        json.loads(line)
        for line in (store / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return sorted((r for r in rows if r["split_unseen"] == subset), key=lambda r: r["episode"])[
        :count
    ]


def full_frames(shard, wanted):
    """First frame of each wanted episode, at the shard's original resolution."""
    handle = pq.ParquetFile(shard)
    out = {}
    for group in range(handle.metadata.num_row_groups):
        table = handle.read_row_group(group, columns=["id", "frame_idx", "image"])
        for episode, index, image in zip(
            table.column("id").to_pylist(),
            table.column("frame_idx").to_pylist(),
            table.column("image").to_pylist(),
            strict=True,
        ):
            if episode in wanted and index == min(wanted[episode]):
                out[episode] = Image.open(io.BytesIO(image["bytes"])).convert("RGB")
        if len(out) == len(wanted):
            break
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--store", type=Path, default=Path("D:/drone_vla_pilot/data/uav_flow_official_20260922")
    )
    parser.add_argument(
        "--shard",
        default="D:/drone_vla_pilot/data/uav_flow_20260921/train-00000-of-00054.parquet",
    )
    parser.add_argument("--episodes", type=int, default=12)
    parser.add_argument("--sizes", type=int, nargs="+", default=[256, 512, 896])
    parser.add_argument("--frame", type=int, default=0, help="which frame of the flight")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    import run_qwen_frd_overfit as api

    chosen = episodes(args.store, "val", args.episodes)
    wanted = {r["episode"]: [args.frame] for r in chosen}
    originals = full_frames(args.shard, wanted)
    processor = api.AutoProcessor.from_pretrained(str(api.MODEL), local_files_only=True)
    model = api.load_base()
    # load_base upcasts norm weights to fp32, which the bf16 activations cannot feed.
    for parameter in model.parameters():
        if parameter.dtype == torch.float32:
            parameter.data = parameter.data.to(torch.bfloat16)
    model.eval()

    def ask(image, instruction):
        text = processor.apply_chat_template(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": QUESTION.format(instruction=instruction)},
                    ],
                }
            ],
            tokenize=False,
            add_generation_prompt=True,
        )
        batch = processor(text=[text], images=[image], return_tensors="pt")
        with torch.inference_mode():
            out = model.generate(**api.cuda(batch), max_new_tokens=4, do_sample=False)
        answer = processor.tokenizer.decode(
            out[0, batch["input_ids"].shape[1] :], skip_special_tokens=True
        )
        answer = answer.strip().lower()
        return "left" if "left" in answer else "right" if "right" in answer else answer

    records, per_size = [], {}
    for size in args.sizes:
        flips, usable, answers = 0, 0, Counter()
        for row in chosen:
            episode = row["episode"]
            if episode not in originals:
                continue
            picture = originals[episode].copy()
            picture.thumbnail((size, size))
            mirrored = ImageOps.mirror(picture)
            a = ask(picture, row["instruction"])
            b = ask(mirrored, row["instruction"])
            answers[a] += 1
            usable += 1
            flips += int({a, b} == {"left", "right"})
            records.append(
                dict(
                    size=size,
                    episode=episode,
                    instruction=row["instruction"],
                    pixels=list(picture.size),
                    answer=a,
                    mirrored_answer=b,
                    flipped=({a, b} == {"left", "right"}),
                )
            )
        per_size[size] = dict(
            flights=usable,
            flipped_with_mirror=flips,
            flip_rate=round(flips / usable, 3) if usable else None,
            answer_counts=dict(answers),
        )
        print(json.dumps({size: per_size[size]}), flush=True)

    summary = dict(
        model=str(api.MODEL),
        question=QUESTION,
        frame=args.frame,
        original_size=list(next(iter(originals.values())).size) if originals else None,
        note=(
            "flip_rate is the share of flights where mirroring the photo flipped the "
            "answer; a model that cannot see the target answers the same both ways"
        ),
        per_size=per_size,
    )
    (OUT / "summary.json").write_text(
        json.dumps(dict(summary=summary, records=records), indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
