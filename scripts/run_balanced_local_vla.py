"""D138 bounded Smol256 mixed-effective-batch runner; two updates are smoke only."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import run_smol_frd_overfit as api
import torch
from peft import LoraConfig, get_peft_model
from run_smol_duration import action_loss, full_split_losses

from uavlab.training.mixed_batches import backward_mixed_batch, balanced_schedule, task_class


def main(args):
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
    deadline = time.monotonic() + 1800

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
        selected = sorted(selected_ids) if args.updates == 2 else list(by_id)
        processor = api.load_processor()
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
        model.requires_grad_(False)
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
        targets = [
            n
            for n, _ in model.named_modules()
            if "text_model.layers." in n
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
            "lora_" in n and "text_model.layers." in n
            for n, p in model.named_parameters()
            if p.requires_grad
        )
        report.update(data_sha256=manifest["index_sha256"], training_schedule=schedule, losses=[])
        if args.updates != 2:
            report["initial_losses"] = split_losses()
        optimizer = torch.optim.AdamW(params, lr=2e-4)
        for step, identities in enumerate(schedule):
            if time.monotonic() > deadline:
                raise RuntimeError("30min wall limit")
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
            chosen = [by_id[k] for k in eval_ids]
            report["after"] = api.predictions(
                model, processor, chosen, [batches[k] for k in eval_ids]
            )
        report.update(
            status="complete",
            peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            sample_exposures=4 * args.updates,
            learned_behavior_claim=False,
        )
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        save()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--condition", choices=["existing_control", "expanded"], required=True)
    p.add_argument("--updates", type=int, choices=[2, 400], default=2)
    main(p.parse_args())
