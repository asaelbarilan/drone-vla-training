"""D153: UAV-Flow endpoint pilot, scored against the text-only baseline from the start.

Task: first frame plus instruction -> final displacement (x, y, z) in metres in the
start frame, emitted as three numbers. Nothing in the prompt enumerates an answer
set, which is the failure the OpenFly panel exposed.

Every evaluation runs twice, once on the real frame and once on a flat gray frame.
A model that scores the same blind is not using the camera, and a model that cannot
beat the frozen text-only baseline in manifest.json is not worth scaling up. Both
numbers are written beside the model's own, so the report cannot flatter itself.
"""

import argparse
import json
import math
import random
import re
import time
from pathlib import Path

import run_smol_frd_overfit as api
import torch
from peft import LoraConfig, get_peft_model
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
ANSWER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")


def target_text(endpoint):
    return " ".join(f"{v:.1f}" for v in endpoint)


def parse(text):
    """First three numbers, but only if the output begins with them.

    Anchoring matters. A loose search scrapes digits out of a prompt the model
    echoed back and scores that as a prediction, so a broken run reports a number
    instead of a failure. Requiring a full match is the opposite error: the first
    run here emitted a trailing fourth number and every prediction was discarded.
    """
    found = ANSWER.match(text)
    return [float(v) for v in found.groups()] if found else None


def load_image(row, gray):
    picture = Image.open(row["image"]).convert("RGB")
    picture.thumbnail((256, 256))
    return Image.new("RGB", picture.size, (127, 127, 127)) if gray else picture


def encode(processor, row, gray=False, with_answer=True):
    image = load_image(row, gray)
    content = [
        {"type": "image", "image": image},
        {"type": "text", "text": PROMPT.format(instruction=row["instruction"])},
    ]
    messages = [{"role": "user", "content": content}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    if not with_answer:
        return processor(text=[text], images=[image], return_tensors="pt")
    prompt_only = processor(text=[text], images=[image], return_tensors="pt")
    # Without a trained stop token the model runs past the third number and keeps
    # emitting digits until the generation limit.
    answer = target_text(row["endpoint_m"]) + (processor.tokenizer.eos_token or "")
    full = processor(text=[text + answer], images=[image], return_tensors="pt")
    labels = full["input_ids"].clone()
    labels[:, : prompt_only["input_ids"].shape[1]] = -100
    full["labels"] = labels
    return full


def evaluate(model, processor, rows, gray):
    """Median final-position error over the validation episodes."""
    model.eval()
    errors, unparsed, raw = [], 0, []
    for row in rows:
        batch = encode(processor, row, gray=gray, with_answer=False)
        with torch.inference_mode():
            tokens = model.generate(
                **api.cuda(batch), max_new_tokens=16, do_sample=False, use_cache=True
            )
        text = processor.tokenizer.decode(
            tokens[0, batch["input_ids"].shape[1] :], skip_special_tokens=True
        )
        raw.append(text)
        guess = parse(text)
        if guess is None:
            unparsed += 1
            continue
        truth = row["endpoint_m"]
        errors.append(math.dist(guess, truth))
    errors.sort()
    model.train()
    return dict(
        n=len(rows),
        parsed=len(errors),
        unparsed=unparsed,
        median_final_error_m=round(errors[len(errors) // 2], 3) if errors else None,
        mean_final_error_m=round(sum(errors) / len(errors), 3) if errors else None,
        sample_outputs=raw[:5],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--updates", type=int, default=400)
    parser.add_argument("--accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--eval-every", type=int, default=200)
    parser.add_argument("--val-limit", type=int, help="Score only the first N validation episodes")
    parser.add_argument("--max-wall-seconds", type=int, default=5400)
    parser.add_argument(
        "--out", type=Path, default=Path("D:/drone_vla_pilot/runs/uav_flow_pilot_20260921_a")
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()

    manifest = json.loads((REPORT / "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(s) for s in (STORE / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    train = [r for r in rows if r["split"] == "train"]
    val = [r for r in rows if r["split"] == "val"]
    if args.val_limit:
        val = val[: args.val_limit]
    assert train and val

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
        task=manifest["task"],
        baseline=manifest["baseline"],
        index_sha256=manifest["index_sha256"],
        updates=args.updates,
        train_episodes=len(train),
        val_episodes=len(val),
        losses=[],
        evaluations=[],
    )

    def save():
        report["elapsed_s"] = round(time.monotonic() - start, 1)
        (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Untrained reference, so any later number is a change and not a claim on its own.
    report["evaluations"].append(
        dict(
            step=0,
            real=evaluate(model, processor, val, False),
            gray=evaluate(model, processor, val, True),
        )
    )
    save()

    rng = random.Random(1153)
    order = []
    model.train()
    for step in range(1, args.updates + 1):
        assert time.monotonic() - start < args.max_wall_seconds, "wall clock budget exhausted"
        total = 0.0
        optimiser.zero_grad(set_to_none=True)
        for _ in range(args.accum):
            if not order:
                order = rng.sample(range(len(train)), len(train))
            batch = encode(processor, train[order.pop()])
            output = model(**api.cuda(batch))
            loss = output.loss / args.accum
            assert torch.isfinite(loss), "non-finite loss"
            loss.backward()
            total += float(loss)
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        optimiser.step()
        report["losses"].append(round(total, 5))
        if step % args.eval_every == 0 or step == args.updates:
            report["evaluations"].append(
                dict(
                    step=step,
                    real=evaluate(model, processor, val, False),
                    gray=evaluate(model, processor, val, True),
                )
            )
            save()
            print(json.dumps(report["evaluations"][-1]["real"] | {"step": step}), flush=True)

    model.save_pretrained(args.out / f"adapter_s{args.updates}")
    report["status"] = "complete"
    report["peak_allocated_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 3)
    save()
    last = report["evaluations"][-1]
    print(
        json.dumps(
            dict(
                text_only_baseline_m=manifest["baseline"]["target_to_beat_m"],
                no_text_baseline_m=manifest["baseline"]["global_no_text"]["median_final_error_m"],
                model_real_m=last["real"]["median_final_error_m"],
                model_gray_m=last["gray"]["median_final_error_m"],
            ),
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
