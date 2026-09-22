"""D155: train a small VLM to emit an 8-step 6-DoF action chunk on UAV-Flow.

Trains only. Scoring lives in score_uav_flow_chunks.py so that the number a run
reports is produced by code that did not also produce the weights - the D153 run
reported 0/88 parsed because its own scorer was wrong, and a separate pass caught
it.

Defaults train on `split_unseen`: no validation episode, instruction wording or
site appears in training. `split_seen` is selectable to measure our own
seen-to-unseen gap, never to report alone.
"""

import argparse
import json
import random
import re
import time
from pathlib import Path

import run_smol_frd_overfit as api
import torch
from peft import LoraConfig, get_peft_model
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/uav_flow_chunks_20260921"
STORE = Path("D:/drone_vla_pilot/data/uav_flow_chunks_20260921")
PROMPT = (
    "Drone forward camera. Task: {instruction} "
    "Predict the next {k} movement steps, in metres and degrees, as {n} numbers: "
    "six per step, x y z then the three rotations."
)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def target_text(chunk, k):
    return " ".join(f"{v:.2f}" for step in chunk[:k] for v in step)


def load_image(row, gray):
    picture = Image.open(row["image"]).convert("RGB")
    picture.thumbnail((256, 256))
    return Image.new("RGB", picture.size, (127, 127, 127)) if gray else picture


def encode(processor, row, k, gray=False, with_answer=True):
    image = load_image(row, gray)
    prompt = PROMPT.format(instruction=row["instruction"], k=k, n=6 * k)
    content = [{"type": "image", "image": image}, {"type": "text", "text": prompt}]
    text = processor.apply_chat_template(
        [{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True
    )
    if not with_answer:
        return processor(text=[text], images=[image], return_tensors="pt")
    prompt_only = processor(text=[text], images=[image], return_tensors="pt")
    answer = target_text(row["chunk"], k) + (processor.tokenizer.eos_token or "")
    full = processor(text=[text + answer], images=[image], return_tensors="pt")
    labels = full["input_ids"].clone()
    labels[:, : prompt_only["input_ids"].shape[1]] = -100
    full["labels"] = labels
    return full


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="split_unseen", choices=["split_unseen", "split_seen"])
    parser.add_argument("--chunk", type=int, default=8)
    parser.add_argument("--updates", type=int, default=800)
    parser.add_argument("--accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--max-wall-seconds", type=int, default=7200)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()

    manifest = json.loads((REPORT / "manifest.json").read_text(encoding="utf-8"))
    baselines = json.loads((REPORT / "baselines.json").read_text(encoding="utf-8"))
    rows = [json.loads(s) for s in (STORE / "steps.jsonl").read_text(encoding="utf-8").splitlines()]
    # A short chunk at the end of an episode would teach a truncated answer shape.
    train = [r for r in rows if r[args.split] == "train" and r["chunk_len"] == args.chunk]
    assert train, "no full-length training chunks"

    processor = api.load_processor()
    model = api.load_base()
    model.enable_input_require_grads()
    prefix = "text_model.layers."
    targets = [
        n
        for n, _ in model.named_modules()
        if prefix in n
        and n.rsplit(".", 1)[-1]
        in {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
    ]
    assert targets
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=32,
            lora_dropout=0,
            target_modules=targets,
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )
    params = [p for p in model.parameters() if p.requires_grad]
    optimiser = torch.optim.AdamW(params, lr=args.lr)

    report = dict(
        status="running",
        split=args.split,
        chunk=args.chunk,
        task=manifest["task"],
        baselines=baselines[args.split],
        steps_sha256=manifest["steps_sha256"],
        train_examples=len(train),
        updates=args.updates,
        losses=[],
    )

    def save():
        report["elapsed_s"] = round(time.monotonic() - start, 1)
        (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    rng = random.Random(1155)
    order = []
    model.train()
    for step in range(1, args.updates + 1):
        assert time.monotonic() - start < args.max_wall_seconds, "wall clock budget exhausted"
        total = 0.0
        optimiser.zero_grad(set_to_none=True)
        for _ in range(args.accum):
            if not order:
                order = rng.sample(range(len(train)), len(train))
            batch = encode(processor, train[order.pop()], args.chunk)
            output = model(**api.cuda(batch))
            loss = output.loss / args.accum
            assert torch.isfinite(loss), "non-finite loss"
            loss.backward()
            total += float(loss)
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        optimiser.step()
        report["losses"].append(round(total, 5))
        if step % 100 == 0:
            save()
            print(json.dumps(dict(step=step, loss=round(total, 4))), flush=True)

    model.save_pretrained(args.out / f"adapter_s{args.updates}")
    report["status"] = "complete"
    report["peak_allocated_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 3)
    save()
    print(
        json.dumps(
            dict(status="complete", first_loss=report["losses"][0], last_loss=report["losses"][-1])
        )
    )


if __name__ == "__main__":
    main()
