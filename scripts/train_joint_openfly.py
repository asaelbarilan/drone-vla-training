"""D144: bounded, source-balanced local + verified atomic OpenFly adapters."""

import argparse
import collections
import functools
import gc
import hashlib
import importlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
import torch
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
from PIL import Image
from run_smol_duration import action_loss

from uavlab.training.direct_vla_frd import parse_target, target_json

DATA = Path("D:/drone_vla_pilot/data/joint_openfly_local_20260917_v1")


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def encode_native(processor, row, qwen):
    images = []
    for path, expected in zip(row["images"], row["image_sha256"], strict=True):
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((256, 256))
            images.append(image)
    content = [{"type": "image", "image": im} for im in images]
    messages = [{"role": "user", "content": [*content, {"type": "text", "text": row["prompt"]}]}]
    answer = str(row["action_id"])
    response = answer if qwen else [{"type": "text", "text": answer}]
    prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    full = processor.apply_chat_template(
        [*messages, {"role": "assistant", "content": response}], tokenize=False
    )
    x = processor(text=[prompt], images=images, return_tensors="pt")
    y = processor(text=[full], images=images, return_tensors="pt")
    n = x.input_ids.shape[1]
    assert torch.equal(x.input_ids, y.input_ids[:, :n]), "native assistant prefix mismatch"
    assert y.input_ids.shape[1] <= 2048, "native token budget exceeded; never truncate"
    labels = y.input_ids.clone()
    labels[:, :n] = -100
    text = answer if qwen else " " + answer
    tokens = processor.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    actual = labels[0, n:].tolist()
    assert actual[: len(tokens["input_ids"])] == tokens["input_ids"]
    suffix = processor.tokenizer.encode(
        "<|im_end|>\n" if qwen else "<end_of_utterance>\n", add_special_tokens=False
    )
    assert actual[len(tokens["input_ids"]) :] == suffix
    digit = [i for i, (a, b) in enumerate(tokens["offset_mapping"]) if answer in text[a:b]]
    assert len(digit) == 1
    weights = torch.zeros_like(labels, dtype=torch.float32)
    other = [i for i in range(len(actual)) if i not in digit]
    assert other
    for i in other:
        weights[0, n + i] = 0.1 / len(other)
    weights[0, n + digit[0]] = 0.9
    y["labels"], y["loss_weights"] = labels, weights
    return x, y


def main(args):
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + args.max_wall_seconds
    report = dict(
        status="initializing",
        model=args.model,
        updates=0,
        losses=[],
        comparable_losses=[],
        smoke_only=args.smoke,
        effective_batch_size=8,
        fresh_base=True,
    )

    def save():
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(args.out / "report.json", report)

    def check_time():
        if time.monotonic() > deadline:
            raise RuntimeError("D144 configured wall limit reached")

    try:
        manifest = json.loads((DATA / "manifest.json").read_text())
        assert (
            hashlib.sha256((DATA / "index.jsonl").read_bytes()).hexdigest()
            == manifest["index_sha256"]
        )
        rows = [json.loads(s) for s in (DATA / "index.jsonl").read_text().splitlines()]
        by = {r["id"]: r for r in rows}
        schedule = manifest["schedules"][: 2 if args.smoke else 400]
        for batch in schedule:
            assert len(batch) == len(set(batch)) == 8
            assert all(by[k]["split"] == "train" for k in batch)
            assert collections.Counter(by[k]["source"] for k in batch) == {"local": 4, "openfly": 4}
            assert {by[k]["group"] for k in batch if by[k]["source"] == "local"} == {
                "motion",
                "hold",
                "stop",
                "visual",
            }
        eval_ids = manifest["evaluation_ids"]
        assert all(by[k]["split"] == "val" for k in eval_ids)
        assert not set(eval_ids) & {k for batch in schedule for k in batch}
        report.update(
            data_sha256=manifest["index_sha256"],
            training_schedule=schedule,
            evaluation_ids=eval_ids,
            max_wall_seconds=args.max_wall_seconds,
        )
        api = importlib.import_module(
            "run_qwen_frd_overfit" if args.model == "qwen" else "run_smol_frd_overfit"
        )
        if args.model == "smol500":
            api.MODEL = Path(
                "D:/drone_vla_pilot/models/SmolVLM-500M-Instruct/a7da5b986cb59b408707209984f360a5f4ad7e47"
            )
        processor = (
            api.AutoProcessor.from_pretrained(str(api.MODEL), local_files_only=True)
            if args.model == "qwen"
            else api.load_processor()
        )
        native_processor = (
            processor
            if args.model == "qwen"
            else api.AutoProcessor.from_pretrained(
                str(api.MODEL),
                local_files_only=True,
                size={"longest_edge": 256},
                do_image_splitting=False,
            )
        )
        report["base"] = str(api.MODEL)

        @functools.lru_cache(maxsize=128)
        def encoded(identity):
            check_time()
            row = by[identity]
            if row["source"] == "openfly":
                return encode_native(native_processor, row, args.model == "qwen")
            path = Path(row["data_root"]) / row["images"]["mosaic"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row["image_sha256"]["mosaic"]
            return api.encode(processor, Path(row["data_root"]), row)

        torch.manual_seed(144)
        torch.cuda.set_per_process_memory_fraction(0.70)
        model = api.load_base()
        if args.model == "qwen":
            model = prepare_model_for_kbit_training(
                model,
                use_gradient_checkpointing=True,
                gradient_checkpointing_kwargs={"use_reentrant": False},
            )
            for name, param in model.named_parameters():
                if param.dtype == torch.float32 and "norm" not in name and not param.requires_grad:
                    param.data = param.data.to(torch.bfloat16)
            prefix = "language_model.layers."
        else:
            model.requires_grad_(False)
            model.gradient_checkpointing_enable(
                gradient_checkpointing_kwargs={"use_reentrant": False}
            )
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
        assert all(
            "lora_" in n and prefix in n for n, p in model.named_parameters() if p.requires_grad
        )

        def loss_for(identity):
            _, batch = encoded(identity)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                output = model(**api.cuda({k: v for k, v in batch.items() if k != "loss_weights"}))
                return action_loss(output.logits, batch)

        train_probe = []
        for source in ("local", "openfly"):
            groups = sorted({r["group"] for r in rows if r["source"] == source})
            for group in groups:
                pool = sorted(
                    [
                        r["id"]
                        for r in rows
                        if r["source"] == source and r["group"] == group and r["split"] == "train"
                    ],
                    key=lambda x: hashlib.sha256(x.encode()).hexdigest(),
                )
                train_probe.extend(pool[:6])
        report["train_loss_probe_ids"] = train_probe

        def measure(step):
            model.eval()
            buckets = collections.defaultdict(list)
            with torch.inference_mode():
                for identity in train_probe + eval_ids:
                    value = float(loss_for(identity))
                    assert torch.isfinite(torch.tensor(value))
                    row = by[identity]
                    buckets[row["source"] + ":" + row["split"]].append(value)
            report["comparable_losses"].append(
                dict(step=step, values={k: sum(v) / len(v) for k, v in buckets.items()})
            )
            save()

        def predict(identities):
            model.eval()
            results = []
            for identity in identities:
                check_time()
                row = by[identity]
                x, _ = encoded(identity)
                proc = native_processor if row["source"] == "openfly" else processor
                with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                    output = model.generate(
                        **api.cuda(x),
                        max_new_tokens=12 if row["source"] == "openfly" else 80,
                        do_sample=False,
                        use_cache=True,
                    )
                raw = proc.tokenizer.decode(
                    output[0, x.input_ids.shape[1] :], skip_special_tokens=True
                )
                if row["source"] == "openfly":
                    parsed = int(raw.strip()) if raw.strip() in {str(a) for a in range(6)} else None
                    target = row["action_id"]
                else:
                    target = row["target"]
                    try:
                        parsed = json.loads(target_json(parse_target(raw)))
                    except (ValueError, TypeError, KeyError):
                        parsed = None
                results.append(
                    dict(
                        id=identity,
                        source=row["source"],
                        group=row["group"],
                        raw=raw,
                        parsed=parsed,
                        target=target,
                        valid=parsed is not None,
                        exact=parsed == target,
                    )
                )
            return results

        report["status"] = "smoke_training" if args.smoke else "baseline_evaluation"
        save()
        if not args.smoke:
            measure(0)
            report["before"] = predict(eval_ids)
            save()
        optimizer = torch.optim.AdamW(params, lr=2e-4)
        report["status"] = "training"
        for step, batch in enumerate(schedule, 1):
            check_time()
            if step == 201:
                optimizer = torch.optim.AdamW(params, lr=5e-5)
            model.train()
            model.config.use_cache = False
            optimizer.zero_grad(set_to_none=True)
            values = collections.defaultdict(list)
            for identity in batch:
                loss = loss_for(identity)
                assert torch.isfinite(loss)
                values[by[identity]["source"]].append(float(loss.detach()))
                (loss / 8).backward()
            norm = torch.nn.utils.clip_grad_norm_(params, 1.0)
            assert torch.isfinite(norm) and norm > 0
            optimizer.step()
            entry = dict(
                step=step,
                loss=sum(sum(v) for v in values.values()) / 8,
                domain_losses={k: sum(v) / len(v) for k, v in values.items()},
                gradient_norm=float(norm),
                sample_ids=batch,
            )
            report["losses"].append(entry)
            report["updates"] = step
            with (args.out / "losses.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            if args.smoke or step % 10 == 0:
                save()
                print(json.dumps(dict(step=step, **entry["domain_losses"])), flush=True)
            if not args.smoke and step % 100 == 0:
                optimizer.zero_grad(set_to_none=True)
                model.save_pretrained(args.out / f"adapter_s{step}")
                measure(step)
        optimizer.zero_grad(set_to_none=True)
        adapter = args.out / f"adapter_s{len(schedule)}"
        model.save_pretrained(adapter)
        report["status"] = "final_evaluation"
        save()
        if not args.smoke:
            report["after"] = predict(eval_ids)
        spots = [
            next(
                k
                for k in eval_ids
                if by[k]["source"] == source
                and (source != "openfly" or by[k]["action_id"] == action)
            )
            for source, action in (("local", 0), ("openfly", 0), ("openfly", 1), ("openfly", 2))
        ]
        expected = predict(spots)
        del optimizer, params, model
        gc.collect()
        torch.cuda.empty_cache()
        model = PeftModel.from_pretrained(api.load_base(), str(adapter), is_trainable=False).eval()
        actual = predict(spots)
        assert [r["raw"] for r in actual] == [r["raw"] for r in expected], "adapter reload mismatch"
        report.update(
            status="complete",
            reload_checks=actual,
            reload_matches=True,
            peak_allocated_gib=torch.cuda.max_memory_allocated() / 1024**3,
        )
        save()
    except Exception as exc:
        report.update(status="failed", error=repr(exc))
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["smol256", "smol500", "qwen"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-wall-seconds", type=int, default=10800)
    main(parser.parse_args())
