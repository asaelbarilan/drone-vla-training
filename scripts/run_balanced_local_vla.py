"""D138 bounded Smol256 mixed-effective-batch runner; two updates are smoke only."""

import argparse
import gc
import hashlib
import importlib
import json
import time
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
from PIL import Image
from run_smol_duration import action_loss, full_split_losses

from uavlab.training.direct_vla_frd import student_prompt
from uavlab.training.mixed_batches import backward_mixed_batch, balanced_schedule, task_class


def main(args):
    api = importlib.import_module(
        "run_qwen_frd_overfit" if args.model == "qwen" else "run_smol_frd_overfit"
    )
    if args.model == "smol500":
        api.MODEL = Path(
            "D:/drone_vla_pilot/models/SmolVLM-500M-Instruct/a7da5b986cb59b408707209984f360a5f4ad7e47"
        )
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(
        status="running",
        updates=0,
        microbatch_size=1,
        effective_batch_size=4,
        condition=args.condition,
        smoke_only=args.updates == 2,
        base=str(api.MODEL),
    )
    deadline = time.monotonic() + args.max_wall_seconds
    started = time.monotonic()

    def save():
        (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    try:
        manifest = json.loads((args.data / "manifest.json").read_text())
        assert (
            hashlib.sha256((args.data / "index.jsonl").read_bytes()).hexdigest()
            == manifest["index_sha256"]
        )
        rows = [json.loads(s) for s in (args.data / "index.jsonl").read_text().splitlines()]
        by_id = {r["decision_id"]: r for r in rows}
        schedule = manifest["schedules"][args.condition][: args.updates]
        condition_rows = (
            rows if args.condition == "expanded" else [r for r in rows if r["seed"] < 1450]
        )
        assert schedule == balanced_schedule(condition_rows, 400)[: args.updates]
        selected_ids = set(k for batch in schedule for k in batch)
        eval_ids = manifest["generation_eval_ids"]
        extra_ids = [
            r["decision_id"]
            for r in rows
            if r["split"] == "val" and r["seed"] >= 1450 and r["task_group"] == "visual"
        ]
        for seed in (1450, 1455, 1460, 1465):
            candidates = [r for r in rows if r["seed"] == seed]
            extra_ids += [
                candidates[round(i * (len(candidates) - 1) / 5)]["decision_id"] for i in range(6)
            ]
        extra_ids += [
            r["decision_id"]
            for r in rows
            if r["split"] == "val" and task_class(r) in ("hold", "stop")
        ]
        extra_ids = list(dict.fromkeys(k for k in extra_ids if k not in eval_ids))
        assert all(by_id[k]["split"] == "val" for k in eval_ids + extra_ids)
        report.update(
            generation_eval_ids=eval_ids,
            extra_eval_ids=extra_ids,
            model=args.model,
            max_wall_seconds=args.max_wall_seconds,
        )
        selected = sorted(selected_ids) if args.updates == 2 else list(by_id)
        processor = (
            api.AutoProcessor.from_pretrained(str(api.MODEL), local_files_only=True)
            if args.model == "qwen"
            else api.load_processor()
        )
        batches = {}
        for identity in selected:
            row = by_id[identity]
            assert (
                hashlib.sha256(
                    (Path(row["data_root"]) / row["images"]["mosaic"]).read_bytes()
                ).hexdigest()
                == row["image_sha256"]["mosaic"]
            )
            batches[identity] = api.encode(processor, Path(row["data_root"]), row)

        def split_losses():
            return {
                name: full_split_losses(api, model, cohort, batches, deadline)
                for name, cohort in {
                    "original": [r for r in rows if r["seed"] < 1450],
                    "new_scenes": [r for r in rows if r["seed"] >= 1450],
                }.items()
            }

        torch.manual_seed(132)
        torch.cuda.set_per_process_memory_fraction(0.70)
        model = api.load_base()
        if args.model == "qwen":
            model = prepare_model_for_kbit_training(
                model,
                use_gradient_checkpointing=True,
                gradient_checkpointing_kwargs={"use_reentrant": False},
            )
            for n, param in model.named_parameters():
                if param.dtype == torch.float32 and "norm" not in n and not param.requires_grad:
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
        params = [p for n, p in model.named_parameters() if p.requires_grad]
        assert all(
            "lora_" in n and prefix in n for n, p in model.named_parameters() if p.requires_grad
        )
        digest = hashlib.sha256()
        for name, param in model.named_parameters():
            if param.requires_grad:
                digest.update(name.encode())
                digest.update(param.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())
        report["initial_adapter_sha256"] = digest.hexdigest()

        def generate(identities):
            results = []
            for identity in identities:
                if time.monotonic() >= deadline:
                    raise RuntimeError("configured wall budget")
                row = by_id[identity]
                result = api.predictions(model, processor, [row], [batches[identity]])[0]
                result["task_group"] = row["task_group"]
                results.append(result)
            return results

        report.update(data_sha256=manifest["index_sha256"], training_schedule=schedule, losses=[])
        if args.updates != 2:
            report["initial_losses"] = split_losses()
            report["before"] = generate(eval_ids)
            save()
        optimizer = torch.optim.AdamW(params, lr=2e-4)
        for step, identities in enumerate(schedule):
            if time.monotonic() > deadline:
                raise RuntimeError("configured wall limit")
            if step == 200:
                optimizer = torch.optim.AdamW(params, lr=5e-5)
            model.train()
            model.config.use_cache = False
            optimizer.zero_grad(set_to_none=True)

            def loss_for(row):
                _, batch = batches[row["decision_id"]]
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    output = model(
                        **api.cuda({k: v for k, v in batch.items() if k != "loss_weights"})
                    )
                    return action_loss(output.logits, batch)

            loss = backward_mixed_batch(identities, by_id, loss_for)
            norm = torch.nn.utils.clip_grad_norm_(params, 1.0)
            assert torch.isfinite(norm) and norm > 0
            optimizer.step()
            entry = dict(
                step=step + 1,
                sample_exposures=(step + 1) * 4,
                sample_ids=identities,
                task_classes=[task_class(by_id[k]) for k in identities],
                loss=loss,
                gradient_norm=float(norm),
            )
            report["losses"].append(entry)
            report["updates"] = step + 1
            with (args.out / "losses.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            if (step + 1) % 25 == 0 or args.updates == 2:
                print(json.dumps(entry), flush=True)
            if args.updates != 2 and (step + 1) % 200 == 0:
                optimizer.zero_grad(set_to_none=True)
                report.setdefault("comparable_losses", []).append(
                    dict(
                        step=step + 1,
                        measurements=split_losses(),
                    )
                )
                model.save_pretrained(args.out / f"adapter_s{step + 1}")
                save()
        if args.updates != 2:
            report["after"] = generate(eval_ids)
            report["extra_after"] = generate(extra_ids)
            save()
            perturb = []
            for kind in ("blank_image", "blank_instruction"):
                for identity in eval_ids:
                    row = by_id[identity]
                    if row["task_group"] != "visual":
                        continue
                    if time.monotonic() >= deadline:
                        raise RuntimeError("configured wall budget")
                    prompt_text = (
                        student_prompt("Perform the requested task.", row["state"])
                        if kind == "blank_instruction"
                        else row["prompt"]
                    )
                    image = (
                        Image.new("RGB", (224, 224), (127, 127, 127))
                        if kind == "blank_image"
                        else Image.open(Path(row["data_root"]) / row["images"]["mosaic"]).convert(
                            "RGB"
                        )
                    )
                    messages = [
                        dict(
                            role="user",
                            content=[
                                dict(type="image", image=image),
                                dict(type="text", text=prompt_text),
                            ],
                        )
                    ]
                    text = processor.apply_chat_template(
                        messages, tokenize=False, add_generation_prompt=True
                    )
                    prompt = processor(text=[text], images=[image], return_tensors="pt")
                    result = api.predictions(model, processor, [row], [(prompt, None)])[0]
                    result.update(intervention=kind, task_group="visual")
                    perturb.append(result)
            report["interventions"] = perturb
            del model, params, optimizer
            gc.collect()
            torch.cuda.empty_cache()
            model = PeftModel.from_pretrained(
                api.load_base(), str(args.out / "adapter_s400"), is_trainable=False
            )
            spots = eval_ids[:2] + eval_ids[-2:]
            report["reloaded_spot_check"] = generate(spots)
            original = {r["decision_id"]: r["raw"] for r in report["after"]}
            report["reload_spot_identical"] = all(
                r["raw"] == original[r["decision_id"]] for r in report["reloaded_spot_check"]
            )
            assert report["reload_spot_identical"]
        report.update(
            status="complete",
            peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            sample_exposures=4 * args.updates,
            learned_behavior_claim=False,
            wall_seconds=time.monotonic() - started,
        )
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        save()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=["smol256", "smol500", "qwen"], default="smol256")
    p.add_argument("--max-wall-seconds", type=int, default=2700)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--condition", choices=["existing_control", "expanded"], required=True)
    p.add_argument("--updates", type=int, choices=[2, 400], default=2)
    main(p.parse_args())
