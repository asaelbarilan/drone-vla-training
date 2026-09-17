"""D137: fixed Smol capacity/duration experiment with comparable full-split losses."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib
import json
import random
import time
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from PIL import Image

from uavlab.training.direct_vla_frd import FIELDS, student_prompt


def dump(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def predict(api, model, processor, rows, batches):
    return api.predictions(model, processor, rows, batches)


def action_loss(logits, batch):
    labels = batch["labels"][:, 1:].to(logits.device)
    active = labels != -100
    values = torch.nn.functional.cross_entropy(
        logits[:, :-1][active].float(), labels[active], reduction="none"
    )
    weights = batch["loss_weights"][:, 1:].to(logits.device)[active]
    return (values * weights).sum() / weights.sum()


def task_class(row):
    if row["task_group"] == "visual":
        return "visual"
    if row["target"]["stop"]:
        return "stop"
    if all(row["target"][k] == 32 for k in FIELDS):
        return "hold"
    return "motion"


def full_split_losses(api, model, rows, batches, deadline):
    model.eval()
    buckets = {}
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        for row in rows:
            if time.monotonic() >= deadline:
                raise RuntimeError("45min job wall budget reached")
            _, batch = batches[row["decision_id"]]
            output = model(**api.cuda({k: v for k, v in batch.items() if k != "loss_weights"}))
            pair = (float(action_loss(output.logits, batch)), float(output.loss))
            for group in ("all", task_class(row)):
                buckets.setdefault((row["split"], group), []).append(pair)
    return [
        dict(
            split=split,
            group=group,
            n=len(values),
            weighted_action_loss=sum(v[0] for v in values) / len(values),
            answer_ce=sum(v[1] for v in values) / len(values),
        )
        for (split, group), values in buckets.items()
    ]


def extended_schedule(train, original):
    rng = random.Random(132)
    schedule = []
    while len(schedule) < 1200:
        order = [r["decision_id"] for r in train]
        rng.shuffle(order)
        schedule.extend(order)
    assert schedule[:400] == original
    return schedule[:1200]


def metrics(predictions):
    groups = {}
    for group in ("coordinate", "visual"):
        records = [r for r in predictions if r["task_group"] == group]
        if not records:
            continue
        maes = [
            sum(abs(r["parsed"][k] - r["target"][k]) for k in FIELDS) / 4 if r["valid"] else 64
            for r in records
        ]
        signs = sum(
            r["valid"] and (r["parsed"]["yaw_cw_bin"] - 32) * (r["target"]["yaw_cw_bin"] - 32) > 0
            for r in records
        )
        velocity_mae = [
            sum(abs(r["parsed"][k] - r["target"][k]) for k in FIELDS[:3]) / 3 * 10 / 64
            if r["valid"]
            else 10
            for r in records
        ]
        yaw_mae = [
            abs(r["parsed"]["yaw_cw_bin"] - r["target"]["yaw_cw_bin"]) * 3 / 64 if r["valid"] else 3
            for r in records
        ]
        constrained_signs = sum(
            r["valid"]
            and not r["parsed"]["stop"]
            and all(r["parsed"][k] == 32 for k in FIELDS[:3])
            and (r["parsed"]["yaw_cw_bin"] - 32) * (r["target"]["yaw_cw_bin"] - 32) > 0
            for r in records
        )
        groups[group] = dict(
            n=len(records),
            valid=sum(r["valid"] for r in records),
            exact=sum(r["exact"] for r in records),
            mean_bin_error=sum(maes) / len(maes),
            correct_yaw_sign=signs,
            correct_yaw_without_translation_or_stop=constrained_signs,
            velocity_mae_mps=sum(velocity_mae) / len(velocity_mae),
            yaw_mae_rps=sum(yaw_mae) / len(yaw_mae),
        )
    return groups


def main(args):
    args.out.mkdir(parents=True, exist_ok=False)
    api = importlib.import_module("run_smol_frd_overfit")
    if args.model == "smol500":
        api.MODEL = Path(
            "D:/drone_vla_pilot/models/SmolVLM-500M-Instruct/"
            "a7da5b986cb59b408707209984f360a5f4ad7e47"
        )
    start_step = 400 if args.resume_adapter else 0
    if args.model == "smol256":
        assert args.resume_adapter, "256 uses preserved step400 adapter"
    wall_deadline = time.monotonic() + 2700
    gate = json.loads(args.gate.read_text())
    assert gate["passed"] and gate["model"] == str(api.MODEL)
    report = dict(
        model=args.model,
        base=str(api.MODEL),
        contract=gate["contract"],
        gate_report=str(args.gate),
        kind="D137 Smol capacity/duration",
        start_step=start_step,
        max_wall_seconds=2700,
        resume_adapter=str(args.resume_adapter) if args.resume_adapter else None,
        status="preflight",
        fresh_adapter=not bool(args.resume_adapter),
    )
    try:
        manifest = json.loads((args.data / "manifest.json").read_text())
        assert (
            hashlib.sha256((args.data / "index.jsonl").read_bytes()).hexdigest()
            == manifest["index_sha256"]
        )
        rows = [json.loads(x) for x in (args.data / "index.jsonl").read_text().splitlines()]
        by_id = {r["decision_id"]: r for r in rows}
        assert len(by_id) == 336
        train = [r for r in rows if r["split"] == "train"]
        val = [r for r in rows if r["split"] == "val"]
        assert len(train) == 252 and len(val) == 84
        assert all(by_id[k]["split"] == "train" for k in manifest["training_schedule"])
        assert all(r["seed"] not in set(range(1, 41)) | set(range(1060, 1065)) for r in rows)
        for r in rows:
            assert r["prompt"] == student_prompt(r["instruction"], r["state"])
            assert (
                hashlib.sha256(
                    (Path(r["data_root"]) / r["images"]["mosaic"]).read_bytes()
                ).hexdigest()
                == r["image_sha256"]["mosaic"]
            )
        schedule = extended_schedule(train, manifest["training_schedule"])
        report["training_schedule"] = schedule
        chosen = [by_id[k] for k in manifest["generation_eval_ids"]]
        processor = api.load_processor()
        batches = {r["decision_id"]: api.encode(processor, Path(r["data_root"]), r) for r in rows}
        report.update(
            data_sha256=manifest["index_sha256"],
            train_ids=[r["decision_id"] for r in train],
            val_ids=[r["decision_id"] for r in val],
            generation_eval_ids=manifest["generation_eval_ids"],
            input_token_range=[
                min(b[1].input_ids.shape[1] for b in batches.values()),
                max(b[1].input_ids.shape[1] for b in batches.values()),
            ],
        )
        dump(args.out / "report.json", report)
        if args.preflight_only:
            report["status"] = "preflight_passed"
            return
        torch.manual_seed(132)
        random.seed(132)
        torch.cuda.set_per_process_memory_fraction(0.70)
        model = api.load_base()
        model.requires_grad_(False)
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
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
        if args.resume_adapter:
            previous = json.loads((args.resume_adapter.parent / "report.json").read_text())
            assert previous["base"] == str(api.MODEL)
            assert previous["data_sha256"] == report["data_sha256"]
            assert previous["updates"] == 400
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
        params = [p for n, p in model.named_parameters() if p.requires_grad]
        assert all(
            "lora_" in n and prefix in n for n, p in model.named_parameters() if p.requires_grad
        )
        report["trainable_parameters"] = sum(p.numel() for p in params)

        def generate(selected):
            if time.monotonic() >= wall_deadline:
                raise RuntimeError("45min job wall budget reached")
            result = predict(
                api, model, processor, selected, [batches[r["decision_id"]] for r in selected]
            )
            for r, s in zip(result, selected, strict=True):
                r["task_group"] = s["task_group"]
            return result

        report["before_kind"] = "step400" if start_step else "zero_shot"
        report["before"] = generate(chosen)
        if start_step:
            assert [r["raw"] for r in report["before"]] == [r["raw"] for r in previous["after"]]
            report["resume_all28_identical"] = True
            report["zero_shot_reference"] = previous["before"]
        else:
            report["zero_shot_reference"] = report["before"]
        report["comparable_losses"] = [
            dict(
                step=start_step,
                measurements=full_split_losses(api, model, rows, batches, wall_deadline),
            )
        ]
        report["generation_checkpoints"] = {str(start_step): report["before"]}
        dump(args.out / "report.json", report)
        losses = []
        for block in range(start_step // 200, 6):
            lr = 2e-4 if block == 0 else 5e-5
            model.train()
            model.config.use_cache = False
            optimizer = torch.optim.AdamW(params, lr=lr)
            started = time.monotonic()
            for within in range(200):
                if time.monotonic() > wall_deadline:
                    raise RuntimeError("45min job wall budget reached")
                if time.monotonic() - started >= 1200:
                    raise RuntimeError("20min block optimization budget reached")
                step = block * 200 + within
                identity = schedule[step]
                _, batch = batches[identity]
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    output = model(
                        **api.cuda({k: v for k, v in batch.items() if k != "loss_weights"})
                    )
                    loss = action_loss(output.logits, batch)
                assert torch.isfinite(loss)
                loss.backward()
                norm = torch.nn.utils.clip_grad_norm_(params, 1.0)
                assert torch.isfinite(norm) and norm > 0
                optimizer.step()
                entry = dict(
                    step=step + 1,
                    sample_id=identity,
                    task_group=by_id[identity]["task_group"],
                    loss=float(loss.detach()),
                    unweighted_token_loss=float(output.loss.detach()),
                    gradient_norm=float(norm),
                    block_seconds=time.monotonic() - started,
                )
                losses.append(entry)
                with (args.out / "losses.jsonl").open("a") as f:
                    f.write(json.dumps(entry) + "\n")
                if (step + 1) % 25 == 0:
                    print(json.dumps(entry), flush=True)
            optimizer.zero_grad(set_to_none=True)
            del optimizer
            report.setdefault("optimization_seconds", []).append(time.monotonic() - started)
            report["comparable_losses"].append(
                dict(
                    step=(block + 1) * 200,
                    measurements=full_split_losses(api, model, rows, batches, wall_deadline),
                )
            )
            if block == 1:
                report["generation_checkpoints"]["400"] = generate(chosen)
            model.save_pretrained(
                args.out / f"adapter_s{(block + 1) * 200}", safe_serialization=True
            )
            dump(args.out / "report.json", report)
        report["after"] = generate(chosen)
        report["generation_checkpoints"]["1200"] = report["after"]
        # Fixed validation interventions; no training follows these results.
        visual = [r for r in chosen if r["task_group"] == "visual"]
        perturb = []
        for kind in ("blank_image", "blank_instruction"):
            for r in visual:
                if time.monotonic() >= wall_deadline:
                    raise RuntimeError("45min job wall budget reached")
                row = dict(r)
                if kind == "blank_instruction":
                    row["prompt"] = student_prompt("Perform the requested task.", r["state"])
                image = (
                    Image.new("RGB", (224, 224), (127, 127, 127))
                    if kind == "blank_image"
                    else Image.open(Path(r["data_root"]) / r["images"]["mosaic"]).convert("RGB")
                )
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": row["prompt"]},
                        ],
                    }
                ]
                text = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                prompt = processor(text=[text], images=[image], return_tensors="pt")
                result = api.predictions(model, processor, [r], [(prompt, None)])[0]
                result["intervention"] = kind
                perturb.append(result)
        report["interventions"] = perturb
        report["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        del model, params, loss, norm, output
        gc.collect()
        torch.cuda.empty_cache()
        model = PeftModel.from_pretrained(
            api.load_base(), str(args.out / "adapter_s1200"), is_trainable=False
        )
        reload_rows = chosen[:2] + chosen[-2:]
        report["reloaded_spot_check"] = generate(reload_rows)
        original = {r["decision_id"]: r["raw"] for r in report["after"]}
        report["reload_spot_identical"] = all(
            original[r["decision_id"]] == r["raw"] for r in report["reloaded_spot_check"]
        )
        assert report["reload_spot_identical"]
        report["before_metrics"] = metrics(report["zero_shot_reference"])
        report["after_metrics"] = metrics(report["after"])
        terminal = [r for r in report["after"] if r["target"]["stop"]]
        assert len(terminal) == 2
        report["pilot_criteria_passed"] = (
            sum(r["valid"] for r in report["after"]) >= 27
            and report["after_metrics"]["visual"]["correct_yaw_without_translation_or_stop"] >= 12
            and all(r["exact"] for r in terminal)
            and report["after_metrics"]["coordinate"]["mean_bin_error"]
            <= 0.8 * report["before_metrics"]["coordinate"]["mean_bin_error"]
        )
        report["status"] = "complete"
        report["updates"] = 1200
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        dump(args.out / "report.json", report)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=["smol256", "smol500"], required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--resume-adapter", type=Path)
    p.add_argument("--gate", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--preflight-only", action="store_true")
    main(p.parse_args())
