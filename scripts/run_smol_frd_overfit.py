"""D136 cached SmolVLM-256M pilot with the same FRD training subset."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import random
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

from uavlab.training.action_value_loss import value_token_weights
from uavlab.training.direct_vla_frd import CONTRACT_ID, parse_target, target_json

MODEL = Path(
    "C:/Users/Asael/.cache/huggingface/hub/models--HuggingFaceTB--SmolVLM-256M-Instruct/snapshots/7e3e67edbbed1bf9888184d9df282b700a323964"
)


def load_processor():
    return AutoProcessor.from_pretrained(
        str(MODEL), local_files_only=True, size={"longest_edge": 512}, do_image_splitting=False
    )


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def subset(rows):
    old = json.loads(Path("reports/vla_local_pilot_20260916/qwen_attempt_c.json").read_text())
    by_id = {r["decision_id"]: r for r in rows}
    selected = [by_id[k] for k in old["selected_ids"]]
    assert all(r["split"] == "train" and r["contract"] == CONTRACT_ID for r in selected)
    assert all(1000 <= r["seed"] <= 1999 and r["seed"] not in range(1060, 1065) for r in selected)
    return selected


def encode(processor, root, row):
    with Image.open(root / row["images"]["mosaic"]) as img:
        image = img.convert("RGB")
    messages = [
        {
            "role": "user",
            "content": [{"type": "image", "image": image}, {"type": "text", "text": row["prompt"]}],
        }
    ]
    prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    full = processor.apply_chat_template(
        [
            *messages,
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": target_json(parse_target(json.dumps(row["target"])))}
                ],
            },
        ],
        tokenize=False,
    )
    x = processor(text=[prompt], images=[image], return_tensors="pt")
    y = processor(text=[full], images=[image], return_tensors="pt")
    n = x.input_ids.shape[1]
    assert torch.equal(x.input_ids, y.input_ids[:, :n]), "assistant prefix mismatch"
    assert y.input_ids.shape[1] <= 1024, "untruncated sample exceeds frozen token budget"
    labels = y.input_ids.clone()
    labels[:, :n] = -100
    assert (labels != -100).sum() > 0
    y["labels"] = labels
    answer = " " + target_json(parse_target(json.dumps(row["target"])))
    tokenized = processor.tokenizer(answer, add_special_tokens=False, return_offsets_mapping=True)
    actual = labels[0, n:].tolist()
    expected = tokenized["input_ids"]
    assert actual[: len(expected)] == expected
    suffix = processor.tokenizer.encode("<end_of_utterance>\n", add_special_tokens=False)
    assert actual[len(expected) :] == suffix
    values, fields = value_token_weights(
        answer, tokenized["offset_mapping"], trailing_tokens=len(suffix)
    )
    weights = torch.zeros_like(labels, dtype=torch.float32)
    weights[0, n:] = torch.tensor(values)
    assert torch.isclose(weights.sum(), torch.tensor(1.0))
    y["loss_weights"] = weights
    return x, y


def load_base():
    model = AutoModelForImageTextToText.from_pretrained(
        str(MODEL), local_files_only=True, torch_dtype=torch.bfloat16, attn_implementation="sdpa"
    ).to("cuda")
    return model


def cuda(batch):
    return {k: v.to("cuda") for k, v in batch.items()}


def predictions(model, processor, rows, batches):
    model.eval()
    results = []
    for row, (prompt, _) in zip(rows, batches, strict=True):
        start = time.monotonic()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            ids = model.generate(**cuda(prompt), max_new_tokens=80, do_sample=False, use_cache=True)
        raw = processor.tokenizer.decode(
            ids[0, prompt.input_ids.shape[1] :], skip_special_tokens=True
        )
        try:
            parsed = json.loads(target_json(parse_target(raw)))
            valid = True
        except (ValueError, TypeError, KeyError):
            parsed, valid = None, False
        results.append(
            {
                "decision_id": row["decision_id"],
                "seed": row["seed"],
                "target": row["target"],
                "raw": raw,
                "parsed": parsed,
                "valid": valid,
                "exact": parsed == row["target"],
                "latency_s": time.monotonic() - start,
            }
        )
        print(json.dumps(results[-1]), flush=True)
    return results


def main():
    global MODEL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume-adapter", type=Path)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    args = parser.parse_args()
    if args.model_path:
        MODEL = args.model_path
    if not 0 < args.learning_rate <= 2e-4:
        raise ValueError("bounded learning rate required")
    if not 1 <= args.steps <= 200:
        raise ValueError("pilot update limit")
    args.out.mkdir(parents=True, exist_ok=False)
    report = {
        "kind": "SmolVLM BF16/LoRA tiny memorization; no generalization claim",
        "contract": CONTRACT_ID,
        "loss": "0.9 equal mean of 5 action value fields + 0.1 format/EOS",
        "shuffle_seed": 132,
        "resume_adapter": str(args.resume_adapter) if args.resume_adapter else None,
        "learning_rate": args.learning_rate,
        "before_kind": "resumed checkpoint" if args.resume_adapter else "zero_shot",
        "model": str(MODEL),
        "max_updates": args.steps,
        "max_optimization_seconds": 1200,
        "status": "preflight",
    }
    try:
        torch.manual_seed(132)
        shuffle_rng = random.Random(132)
        torch.cuda.set_per_process_memory_fraction(0.70)
        rows = [json.loads(x) for x in (args.data / "index.jsonl").read_text().splitlines()]
        conversion = json.loads(
            Path("reports/vla_frd_followup_20260916/conversion.json").read_text()
        )
        assert conversion["contract"] == CONTRACT_ID
        assert (
            hashlib.sha256((args.data / "index.jsonl").read_bytes()).hexdigest()
            == conversion["index_sha256"]
        )
        chosen = subset(rows)
        report["data_sha256"] = hashlib.sha256((args.data / "index.jsonl").read_bytes()).hexdigest()
        report["selected_ids"] = [r["decision_id"] for r in chosen]
        processor = load_processor()
        batches = [encode(processor, args.data, r) for r in chosen]
        report["token_lengths"] = [y.input_ids.shape[1] for _, y in batches]
        dump(args.out / "report.json", report)
        if args.preflight_only:
            report["status"] = "preflight_passed"
            return
        model = load_base()
        model.requires_grad_(False)
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
        targets = [
            n
            for n, m in model.named_modules()
            if "text_model.layers." in n
            and n.rsplit(".", 1)[-1]
            in {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
        ]
        assert targets and all("visual" not in n for n in targets)
        if args.resume_adapter:
            previous = json.loads((args.resume_adapter.parent / "report.json").read_text())
            assert previous["model"] == str(MODEL)
            assert previous["contract"] == CONTRACT_ID
            assert previous["selected_ids"] == report["selected_ids"]
            assert previous["data_sha256"] == report["data_sha256"]
            report["previous_updates"] = previous["updates"]
            model = PeftModel.from_pretrained(model, str(args.resume_adapter), is_trainable=True)
        else:
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
        trainable = [(n, p) for n, p in model.named_parameters() if p.requires_grad]
        assert trainable and all("lora_" in n and "text_model" in n for n, _ in trainable)
        report["trainable_parameters"] = sum(p.numel() for _, p in trainable)
        report["target_modules"] = targets
        report["loaded_allocated_bytes"] = torch.cuda.memory_allocated()
        report["status"] = "loaded"
        dump(args.out / "report.json", report)
        # All 16 frozen TRAIN examples, before this bounded optimization attempt.
        report["before"] = predictions(model, processor, chosen, batches)
        dump(args.out / "report.json", report)
        model.train()
        model.config.use_cache = False
        optimizer = torch.optim.AdamW([p for _, p in trainable], lr=args.learning_rate)
        losses = []
        start = time.monotonic()
        for step in range(args.steps):
            if time.monotonic() - start >= 1200:
                break
            if step % len(batches) == 0:
                order = list(range(len(batches)))
                shuffle_rng.shuffle(order)
            selected_index = order[step % len(batches)]
            _, batch = batches[selected_index]
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                output = model(**cuda({k: v for k, v in batch.items() if k != "loss_weights"}))
                expected = batch["labels"][:, 1:].to("cuda")
                active = expected != -100
                token_loss = torch.nn.functional.cross_entropy(
                    output.logits[:, :-1][active].float(), expected[active], reduction="none"
                )
                weights = batch["loss_weights"][:, 1:].to("cuda")[active]
                loss = (token_loss * weights).sum() / weights.sum()
            if not torch.isfinite(loss):
                raise ValueError("nonfinite loss")
            loss.backward()
            grads = [p.grad for _, p in trainable if p.grad is not None]
            if not grads or not all(torch.isfinite(g).all() for g in grads):
                raise ValueError("missing/nonfinite adapter gradients")
            norm = torch.nn.utils.clip_grad_norm_([p for _, p in trainable], 1.0)
            if not torch.isfinite(norm) or norm <= 0:
                raise ValueError("zero/nonfinite gradient norm")
            optimizer.step()
            entry = {
                "step": step + 1,
                "sample_id": chosen[selected_index]["decision_id"],
                "unweighted_token_loss": float(output.loss.detach()),
                "loss": float(loss.detach()),
                "gradient_norm": float(norm),
                "seconds": time.monotonic() - start,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            }
            losses.append(entry)
            with (args.out / "losses.jsonl").open("a") as f:
                f.write(json.dumps(entry) + "\n")
            if step == 0 or (step + 1) % 10 == 0:
                print(json.dumps(entry), flush=True)
            if step == 0:
                report["first_backward_passed"] = True
                dump(args.out / "report.json", report)
        report["updates"] = len(losses)
        report["optimization_seconds"] = time.monotonic() - start
        optimizer.zero_grad(set_to_none=True)
        del optimizer
        model.save_pretrained(args.out / "adapter", safe_serialization=True)
        processor.save_pretrained(args.out / "adapter")
        report["after"] = predictions(model, processor, chosen, batches)
        dump(args.out / "report.json", report)
        del model, trainable, grads, loss, norm, output, token_loss, weights
        gc.collect()
        torch.cuda.empty_cache()
        model = PeftModel.from_pretrained(
            load_base(), str(args.out / "adapter"), is_trainable=False
        )
        report["reloaded"] = predictions(model, processor, chosen, batches)
        report["reload_identical"] = [r["raw"] for r in report["after"]] == [
            r["raw"] for r in report["reloaded"]
        ]
        report["valid_count"] = sum(r["valid"] for r in report["after"])
        report["exact_count"] = sum(r["exact"] for r in report["after"])
        report["loss_decreased"] = sum(x["loss"] for x in losses[-16:]) / len(losses[-16:]) < sum(
            x["loss"] for x in losses[:16]
        ) / len(losses[:16])
        report["hold_stop_exact"] = all(r["exact"] for r in report["after"][:8])
        report["passed"] = (
            report["reload_identical"]
            and report["valid_count"] >= 15
            and report["exact_count"] >= 14
            and report["loss_decreased"]
            and report["hold_stop_exact"]
        )
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["peak_allocated_bytes"] = (
            torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0
        )
        dump(args.out / "report.json", report)


if __name__ == "__main__":
    main()
