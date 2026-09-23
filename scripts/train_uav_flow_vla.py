"""D155: UAV-Flow chunk training with the official action-token representation.

Follows OpenVLA-UAV/vla-scripts/finetune_uav.py where the hardware allows: 256-bin
action tokens on the vocabulary tail, LoRA rank 32, learning rate 5e-4, no image
augmentation. It cannot follow the base model - the recipe fine-tunes openvla-7b
across 8 GPUs, and this runs a 256M/500M VLM on one 8 GB card. That substitution
is deliberate and no number from here is comparable to a published one.

Action tokens are spliced into `input_ids` by id. They are NOT rendered to text
and re-encoded: a measured 177 of 200 chunks come back as different ids that way,
because the repurposed vocabulary tail holds ordinary word-pieces that BPE
re-merges. The official implementation works on ids for the same reason.
"""

import argparse
import contextlib
import importlib
import itertools
import json
import math
import os
import random
import re
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from peft import (
    LoraConfig,
    get_peft_model,
    load_peft_weights,
    prepare_model_for_kbit_training,
    set_peft_model_state_dict,
)
from PIL import Image, ImageOps
from uav_flow_action_tokenizer import ActionTokenizer, load_stats

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/uav_flow_chunks_20260921"
STORE = Path(os.environ.get("UAV_FLOW_STORE", "D:/drone_vla_pilot/data/uav_flow_chunks_20260921"))
PROMPT = "Drone forward camera. What action should the drone take to {instruction}?"
# D158: the official OpenVLA-UAV format (prepare_uav_flow_official.py).
OFFICIAL_REPORT = ROOT / "reports/uav_flow_official_20260922"
OFFICIAL_STORE = Path(
    os.environ.get("UAV_FLOW_OFFICIAL_STORE", "D:/drone_vla_pilot/data/uav_flow_official_20260922")
)
OFFICIAL_PROMPT = "Current State: {state}, What action should the uav take to {instruction}?"
OFFICIAL_REPEAT = 5
SMOL500 = "D:/drone_vla_pilot/models/SmolVLM-500M-Instruct/a7da5b986cb59b408707209984f360a5f4ad7e47"


def setup(model_name, precision="nf4"):
    """Load a base model the way this repository already loads it, and say which
    layer prefix LoRA should attach to. Qwen is 4-bit with gradient checkpointing,
    which leaves its vision tower frozen - the expert-only regime Exp2VLA uses.

    precision="bf16" loads the unquantised base (cloud GPUs). D157 found about
    40% of the PyTorch-vs-llama.cpp token disagreement came from quantisation,
    and the NF4 reference could not separate the rest; training against the true
    weights removes NF4 from the chain."""
    api = importlib.import_module(
        "run_qwen_frd_overfit" if model_name == "qwen" else "run_smol_frd_overfit"
    )
    if model_name == "smol500":
        api.MODEL = Path(SMOL500)
    if model_name == "qwen" and precision == "bf16":
        processor = api.AutoProcessor.from_pretrained(str(api.MODEL), local_files_only=True)
        model = api.Qwen3VLForConditionalGeneration.from_pretrained(
            str(api.MODEL),
            local_files_only=True,
            torch_dtype=torch.bfloat16,
            device_map={"": torch.cuda.current_device()},
            attn_implementation="sdpa",
        )
        model.requires_grad_(False)
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
        return api, processor, model, "language_model.layers."
    if model_name == "qwen":
        processor = api.AutoProcessor.from_pretrained(str(api.MODEL), local_files_only=True)
        model = prepare_model_for_kbit_training(
            api.load_base(),
            use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
        )
        # run_qwen_frd_overfit.load_base upcasts norm weights to fp32, which the
        # bf16 activations here cannot feed. Keep the whole frozen base in bf16.
        for param in model.parameters():
            if param.dtype == torch.float32 and not param.requires_grad:
                param.data = param.data.to(torch.bfloat16)
        return api, processor, model, "language_model.layers."
    processor = api.load_processor()
    model = api.load_base()
    model.requires_grad_(False)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    return api, processor, model, "text_model.layers."


SIDES = {
    "left": "right",
    "right": "left",
    "leftward": "rightward",
    "rightward": "leftward",
    "clockwise": "counterclockwise",
    "counterclockwise": "clockwise",
    "anticlockwise": "clockwise",
}
# longest first, so "counterclockwise" is matched before "clockwise"
SIDE_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(SIDES, key=len, reverse=True)) + r")\b", re.IGNORECASE
)


def mirror_instruction(text):
    """Swap the side words in one pass, keeping capitalisation."""

    def swap(match):
        word = match.group(0)
        other = SIDES[word.lower()]
        return other.capitalize() if word[0].isupper() else other

    return SIDE_PATTERN.sub(swap, text)


def mirror_row(row):
    """A left-right mirrored copy: photo flipped at load, sideways and yaw negated,
    side words swapped. Free data that teaches exactly the grounding we fail."""
    return {
        **row,
        "id": row["id"] + ":m",
        "mirror": True,
        "instruction": mirror_instruction(row["instruction"]),
        "prompt": mirror_instruction(row["prompt"]),
        "chunk": [[dx, -dy, dz, -dyaw] for dx, dy, dz, dyaw in row["chunk"]],
    }


def image_path(row):
    """Frames are stored with absolute Windows paths; on another machine the same
    frame lives under UAV_FLOW_STORE/frames/<episode>/<file>."""
    path = Path(row["image"].replace("\\", "/"))
    if path.exists():
        return path
    store = OFFICIAL_STORE if row.get("format") == "official" else STORE
    return store / "frames" / path.parent.name / path.name


def official_rows(split, k, instruction="instruction", oversample=False, mirror=False):
    """Per-frame examples in the official format, with a K-step target.

    The target is actions[t : t+K], each step in the drone frame at that step; past
    the end of the flight it is padded with zero actions, which is what the
    official data uses for the last frame. K=1 is exactly the official sample.
    `instruction`: "instruction" (official, free wording), "instruction_unified",
    or "both" (alternates by frame, so each flight is seen with both wordings).
    With oversample=True the first and last frames are repeated 5 extra times.
    """
    rows = []
    for line in (OFFICIAL_STORE / "episodes.jsonl").read_text(encoding="utf-8").splitlines():
        episode = json.loads(line)
        if episode["split_unseen"] != split:
            continue
        actions, n = episode["actions"], len(episode["actions"])
        for t in range(n):
            if instruction == "both":
                key = "instruction" if t % 2 == 0 else "instruction_unified"
            else:
                key = instruction
            chunk = actions[t : t + k]
            chunk = chunk + [[0.0] * 4] * (k - len(chunk))
            state = ",".join(str(round(float(x), 1)) for x in episode["proprio"][t])
            row = dict(
                format="official",
                id=f"{episode['episode']}:{t:05d}",
                episode=episode["episode"],
                step=t,
                image=episode["images"][t],
                prompt=OFFICIAL_PROMPT.format(state=state, instruction=episode[key]),
                instruction=episode[key],
                chunk=chunk,
                chunk_len=k,
            )
            repeats = 1 + (OFFICIAL_REPEAT if oversample and t in (0, n - 1) else 0)
            rows.extend([row] * repeats)
            if mirror:
                rows.extend([mirror_row(row)] * repeats)
    return rows


def official_stats():
    manifest = json.loads((OFFICIAL_REPORT / "manifest.json").read_text(encoding="utf-8"))
    return manifest["action_stats_train"]


def load_image(row, gray=False):
    picture = Image.open(image_path(row)).convert("RGB")
    picture.thumbnail((256, 256))
    if row.get("mirror"):
        picture = ImageOps.mirror(picture)
    return Image.new("RGB", picture.size, (127, 127, 127)) if gray else picture


def encode(processor, tokenizer, row, k, gray=False, with_answer=True, image=None):
    image = load_image(row, gray) if image is None else image
    text = processor.apply_chat_template(
        [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {
                        "type": "text",
                        "text": row["prompt"]
                        if "prompt" in row
                        else PROMPT.format(instruction=row["instruction"].rstrip(".").lower()),
                    },
                ],
            }
        ],
        tokenize=False,
        add_generation_prompt=True,
    )
    batch = processor(text=[text], images=[image], return_tensors="pt")
    if not with_answer:
        return batch
    prompt_length = batch["input_ids"].shape[1]
    ids = [*tokenizer.token_ids(row["chunk"][:k]), processor.tokenizer.eos_token_id]
    answer = torch.tensor([ids], dtype=batch["input_ids"].dtype)
    batch["input_ids"] = torch.cat([batch["input_ids"], answer], dim=1)
    batch["attention_mask"] = torch.cat([batch["attention_mask"], torch.ones_like(answer)], dim=1)
    # transformers 5 also returns per-token type ids (mm_token_type_ids); the
    # answer is plain text, which is type 0.
    for key in ("mm_token_type_ids", "token_type_ids"):
        if key in batch:
            batch[key] = torch.cat([batch[key], torch.zeros_like(answer)], dim=1)
    labels = batch["input_ids"].clone()
    labels[:, :prompt_length] = -100
    batch["labels"] = labels
    return batch


# Per-token fields and their padding value (None = the tokenizer's pad id).
# Everything else in an encoded example (pixel_values, image_grid_thw, ...) is
# per-image and concatenates as is.
SEQUENCE_FILL = dict(
    input_ids=None, attention_mask=0, labels=-100, mm_token_type_ids=0, token_type_ids=0
)


def collate_left(items, pad_id):
    """Left-padded batch for generation: decoder-only models continue from the
    last position, so the padding has to sit in front, not behind."""
    width = max(item["input_ids"].shape[1] for item in items)
    batch = {}
    for key in items[0]:
        if key in SEQUENCE_FILL and key != "labels":
            fill = pad_id if SEQUENCE_FILL[key] is None else SEQUENCE_FILL[key]
            parts = [F.pad(i[key], (width - i[key].shape[1], 0), value=fill) for i in items]
        elif key == "labels":
            continue
        else:
            parts = [i[key] for i in items]
        batch[key] = torch.cat(parts, dim=0)
    return batch


def collate(items, pad_id):
    """Right-pad single-example encodings into one batch. Every answer is the same
    49 tokens, so the model's token-mean loss is also the per-example mean."""
    width = max(item["input_ids"].shape[1] for item in items)
    batch = {}
    for key in items[0]:
        if key in SEQUENCE_FILL:
            fill = pad_id if SEQUENCE_FILL[key] is None else SEQUENCE_FILL[key]
            parts = [F.pad(i[key], (0, width - i[key].shape[1]), value=fill) for i in items]
        else:
            parts = [i[key] for i in items]
        batch[key] = torch.cat(parts, dim=0)
    return batch


class Examples(torch.utils.data.Dataset):
    """Encodes on DataLoader workers so image decoding overlaps the GPU step."""

    def __init__(self, processor, tokenizer, rows, k):
        self.processor, self.tokenizer, self.rows, self.k = processor, tokenizer, rows, k

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        return encode(self.processor, self.tokenizer, self.rows[index], self.k)


class Collate:
    def __init__(self, pad_id):
        self.pad_id = pad_id

    def __call__(self, items):
        return collate(items, self.pad_id)


class ExampleOrder(torch.utils.data.Sampler):
    """The same shuffled-epoch stream the batch-1 trainer used (a fresh
    permutation per epoch, consumed from the end), resumable by skipping the
    examples already seen."""

    def __init__(self, n, seed, skip, rank=0, world=1):
        self.n, self.seed, self.skip, self.rank, self.world = n, seed, skip, rank, world

    def __iter__(self):
        rng = random.Random(self.seed)

        def stream():
            while True:
                yield from reversed(rng.sample(range(self.n), self.n))

        # Under torchrun every rank walks the same global stream and takes every
        # world-th example, so the ranks never see the same example in one update.
        return itertools.islice(stream(), self.skip + self.rank, None, self.world)


def distributed():
    """(rank, local rank, world size); a no-op unless launched with torchrun."""
    world = int(os.environ.get("WORLD_SIZE", "1"))
    local = int(os.environ.get("LOCAL_RANK", "0"))
    torch.cuda.set_device(local)
    if world > 1:
        torch.distributed.init_process_group("nccl")
    return int(os.environ.get("RANK", "0")), local, world


def learning_rate(args, step):
    if args.schedule == "constant":
        return args.lr
    warmup = max(1, round(args.warmup * args.updates))
    if step <= warmup:
        return args.lr * step / warmup
    progress = (step - warmup) / max(1, args.updates - warmup)
    return args.lr * 0.5 * (1 + math.cos(math.pi * progress))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen", choices=["smol256", "smol500", "qwen"])
    parser.add_argument("--split", default="split_unseen", choices=["split_unseen", "split_seen"])
    parser.add_argument("--chunk", type=int, default=8, help="prediction horizon K (steps)")
    parser.add_argument(
        "--format",
        default="d155",
        choices=["d155", "official"],
        help="official = OpenVLA-UAV: 4-D drone-frame actions, state in the prompt",
    )
    parser.add_argument(
        "--mirror",
        action="store_true",
        help="official format: add a left-right mirrored copy of every training example",
    )
    parser.add_argument(
        "--instruction",
        default="instruction",
        choices=["instruction", "instruction_unified", "both"],
        help="official format only; the official code uses `instruction`",
    )
    parser.add_argument("--updates", type=int, default=800)
    parser.add_argument("--batch-size", type=int, default=1, help="examples per forward pass")
    parser.add_argument("--accum", type=int, default=8, help="forward passes per update")
    parser.add_argument("--workers", type=int, default=0, help="DataLoader encode workers")
    parser.add_argument("--schedule", default="constant", choices=["constant", "cosine"])
    parser.add_argument("--warmup", type=float, default=0.03, help="cosine warmup fraction")
    parser.add_argument("--save-every", type=int, default=0, help="checkpoint every N updates")
    parser.add_argument("--resume", action="store_true", help="continue from OUT/checkpoint")
    parser.add_argument("--epochs", type=float, help="set --updates from passes over train")
    parser.add_argument("--wandb-project", help="log to Weights & Biases (needs WANDB_API_KEY)")
    parser.add_argument("--wandb-entity", default="asael", help="team that owns the project")
    parser.add_argument("--lr", type=float, default=5e-4, help="official recipe value")
    parser.add_argument("--lora-rank", type=int, default=32, help="official recipe value")
    parser.add_argument(
        "--targets",
        default="all-linear",
        choices=["all-linear", "text-only"],
        help="all-linear matches the recipe and trains the visual path too",
    )
    parser.add_argument(
        "--precision",
        default="nf4",
        choices=["nf4", "bf16"],
        help="bf16 = unquantised base, needs about 9 GB more VRAM than nf4",
    )
    parser.add_argument("--val-every", type=int, default=50)
    parser.add_argument("--val-batches", type=int, default=160)
    parser.add_argument("--max-wall-seconds", type=int, default=7200)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rank, local, world = distributed()
    main_rank = rank == 0
    if main_rank:
        args.out.mkdir(parents=True, exist_ok=args.resume)
    checkpoint = args.out / "checkpoint"
    start = time.monotonic()

    if args.format == "official":
        assert args.split == "split_unseen", "the official data carries the unseen split only"
        manifest = json.loads((OFFICIAL_REPORT / "manifest.json").read_text(encoding="utf-8"))
        manifest["task"] = (
            f"current frame + state + instruction -> next {args.chunk} (dx,dy,dz,dyaw), drone frame"
        )
        manifest["steps_sha256"] = manifest["episodes_sha256"]
        baselines = None
        stats = official_stats()
        train = official_rows(
            "train", args.chunk, args.instruction, oversample=True, mirror=args.mirror
        )
        held = official_rows("val", args.chunk, args.instruction)
    else:
        manifest = json.loads((REPORT / "manifest.json").read_text(encoding="utf-8"))
        baselines = json.loads((REPORT / "baselines.json").read_text(encoding="utf-8"))[args.split]
        stats = load_stats(args.split)
        rows = [
            json.loads(s) for s in (STORE / "steps.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        train = [r for r in rows if r[args.split] == "train" and r["chunk_len"] == args.chunk]
        held = [r for r in rows if r[args.split] == "val" and r["chunk_len"] == args.chunk]
    assert train and held, "need full-length chunks on both sides"
    # A fixed held-out sample, so every point on the curve is the same examples.
    held = random.Random(9).sample(held, min(args.val_batches, len(held)))
    per_update = args.batch_size * args.accum * world
    if args.epochs:
        args.updates = math.ceil(args.epochs * len(train) / per_update)

    api, processor, model, prefix = setup(args.model, args.precision)
    globals()["api"] = api
    tokenizer = ActionTokenizer(processor.tokenizer, stats)
    # The official recipe uses target_modules="all-linear", which covers the vision
    # encoder and the projector. Restricting LoRA to the language layers leaves the
    # whole visual path frozen, and the model then learns a text-to-action lookup:
    # the D155 "b" run scored 2.86 m on episodes it trained on, 12.09 m held out,
    # and moved 1 cm when its images were replaced by flat gray.
    if args.targets == "all-linear":
        targets = "all-linear"
        covered = sorted(
            {
                ".".join(n.split(".")[:3])
                for n, m in model.named_modules()
                if isinstance(m, torch.nn.Linear)
            }
        )
    else:
        targets = [
            n
            for n, _ in model.named_modules()
            if prefix in n
            and n.rsplit(".", 1)[-1]
            in {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
        ]
        assert targets
        covered = ["text_model"]
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.lora_rank,
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
        model=args.model,
        base=str(api.MODEL),
        recipe=dict(
            follows="OpenVLA-UAV finetune_uav.sh",
            action_tokens=256,
            lora_rank=args.lora_rank,
            learning_rate=args.lr,
            image_aug=False,
            target_modules=args.targets,
            deviation="base model is SmolVLM-256M on one GPU, not openvla-7b on eight",
        ),
        split=args.split,
        chunk=args.chunk,
        task=manifest["task"],
        baselines=baselines,
        steps_sha256=manifest["steps_sha256"],
        action_stats=stats,
        data_format=args.format,
        mirrored=args.mirror,
        instruction_field=args.instruction if args.format == "official" else "instruction_unified",
        trainable_module_roots=covered,
        train_examples=len(train),
        held_out_examples=len(held),
        updates=args.updates,
        precision=args.precision,
        accum=args.accum,
        batch_size=args.batch_size,
        world_size=world,
        examples_per_update=per_update,
        epochs=round(args.updates * per_update / len(train), 3),
        schedule=args.schedule,
        losses=[],
        seconds_per_update=[],
        held_out=[],
    )

    def save():
        if not main_rank:
            return
        report["elapsed_s"] = round(time.monotonic() - start, 1)
        (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    first = 1
    if args.resume:
        state = torch.load(checkpoint / "state.pt", weights_only=False)
        set_peft_model_state_dict(model, load_peft_weights(str(checkpoint)))
        optimiser.load_state_dict(state["optimiser"])
        report = state["report"]
        first = state["step"] + 1
        report.setdefault("resumed_at", []).append(state["step"])

    core = model
    if world > 1:
        model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[local])

    run = None
    if args.wandb_project and main_rank:
        import wandb

        run = wandb.init(
            project=args.wandb_project,
            entity=args.wandb_entity,
            name=args.out.name,
            id=args.out.name,
            resume="allow",
            config={k: str(v) for k, v in vars(args).items()} | dict(world_size=world),
        )

    def save_checkpoint(step):
        if not main_rank:
            return
        core.save_pretrained(checkpoint)
        torch.save(
            dict(step=step, optimiser=optimiser.state_dict(), report=report),
            checkpoint / "state.pt.tmp",
        )
        os.replace(checkpoint / "state.pt.tmp", checkpoint / "state.pt")
        # Keep every checkpointed adapter so the best held-out point can be picked.
        core.save_pretrained(args.out / f"adapter_s{step}")

    pad_id = processor.tokenizer.pad_token_id
    loader = iter(
        torch.utils.data.DataLoader(
            Examples(processor, tokenizer, train, args.chunk),
            batch_size=args.batch_size,
            sampler=ExampleOrder(len(train), 1155, (first - 1) * per_update, rank, world),
            num_workers=args.workers,
            collate_fn=Collate(pad_id),
            prefetch_factor=4 if args.workers else None,
            persistent_workers=bool(args.workers),
        )
    )
    # Each rank scores its own share of the fixed held-out sample.
    mine = held[rank::world]
    held_batches = [
        collate(
            [encode(processor, tokenizer, r, args.chunk) for r in mine[i : i + args.batch_size]],
            pad_id,
        )
        for i in range(0, len(mine), args.batch_size)
    ]

    def reduced(value):
        if world == 1:
            return value
        tensor = torch.tensor([value], device="cuda", dtype=torch.float64)
        torch.distributed.all_reduce(tensor)
        return float(tensor)

    model.train()
    for step in range(first, args.updates + 1):
        assert time.monotonic() - start < args.max_wall_seconds, "wall clock budget exhausted"
        total = 0.0
        tick = time.monotonic()
        for group in optimiser.param_groups:
            group["lr"] = learning_rate(args, step)
        optimiser.zero_grad(set_to_none=True)
        for micro in range(args.accum):
            # Gradients only need averaging across GPUs on the last micro-batch.
            last = micro == args.accum - 1
            sync = contextlib.nullcontext() if world == 1 or last else model.no_sync()
            with sync:
                output = model(**api.cuda(next(loader)))
                loss = output.loss / args.accum
                assert torch.isfinite(loss), "non-finite loss"
                loss.backward()
            total += float(loss)
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        optimiser.step()
        total = reduced(total) / world
        report["losses"].append(round(total, 5))
        report["seconds_per_update"].append(round(time.monotonic() - tick, 3))
        if step % args.val_every == 0 or step == 1:
            core.eval()
            with torch.inference_mode():
                values = [
                    float(core(**api.cuda(b)).loss) * b["input_ids"].shape[0] for b in held_batches
                ]
            core.train()
            held_loss = reduced(sum(values)) / len(held)
            report["held_out"].append(dict(step=step, loss=round(held_loss, 5)))
            if run:
                run.log(dict(held_out_loss=held_loss), step=step)
        if run:
            run.log(
                dict(
                    train_loss=total,
                    lr=optimiser.param_groups[0]["lr"],
                    seconds_per_update=report["seconds_per_update"][-1],
                    epoch=step * per_update / len(train),
                ),
                step=step,
            )
        if args.save_every and step % args.save_every == 0:
            save_checkpoint(step)
        if not main_rank:
            continue
        if step % 100 == 0:
            save()
            print(json.dumps(dict(step=step, loss=round(total, 4))), flush=True)
        elif step <= 10 or step % 10 == 0:
            seconds = report["seconds_per_update"][-1]
            print(json.dumps(dict(step=step, loss=round(total, 4), s=seconds)), flush=True)

    report["status"] = "complete"
    report["peak_allocated_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 3)
    if main_rank:
        core.save_pretrained(args.out / f"adapter_s{args.updates}")
        save()
        print(json.dumps(dict(first_loss=report["losses"][0], last_loss=report["losses"][-1])))
    if run:
        run.finish()
    if world > 1:
        torch.distributed.destroy_process_group()


if __name__ == "__main__":
    main()
