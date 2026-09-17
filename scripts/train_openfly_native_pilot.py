# ruff: noqa: E501
"""D142 Smol500 native-ID pipeline test; isolated from previous FRD policies."""

import gc
import hashlib
import json
import os
import random
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
import run_smol_frd_overfit as api
import torch
from peft import LoraConfig, PeftModel, get_peft_model
from PIL import Image
from transformers import AutoProcessor

ROOT = Path("D:/drone_vla_pilot/data/openfly_train_pilot_20260917")
OUT = Path("D:/drone_vla_pilot/runs/smol500_openfly_native_20260917_a")
REPORT = Path("reports/vla_openfly_train_20260917")
api.MODEL = Path(
    "D:/drone_vla_pilot/models/SmolVLM-500M-Instruct/a7da5b986cb59b408707209984f360a5f4ad7e47"
)
PROMPT = "Follow this visual drone route. Images are oldest to newest: two past observations and the current front view. Choose the next native OpenFly action ID. Output exactly one digit, no prose. IDs: 0=mission stop, 1=forward 3m, 2=turn left, 3=turn right, 4=up, 5=down, 6=move left, 7=move right, 8=forward 6m, 9=forward 9m. These are discrete dataset primitives, not velocity setpoints. Route: "


def write(report):
    text = json.dumps(report, indent=2)
    (OUT / "report.json").write_text(text, encoding="utf-8")
    (REPORT / "training_report.json").write_text(text, encoding="utf-8")
    losses = (
        [json.loads(x) for x in (OUT / "losses.jsonl").read_text().splitlines()]
        if (OUT / "losses.jsonl").exists()
        else []
    )
    Path("reports/vla_dataset_review_20260916/openfly_training_status.json").write_text(
        json.dumps(dict(report=report, losses=losses)), encoding="utf-8"
    )


def encode(processor, row, blank=False):
    images = []
    for path, sha in zip(row["images"], row["image_sha256"], strict=True):
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((256, 256))
        images.append(Image.new("RGB", image.size) if blank else image)
    messages = [
        dict(
            role="user",
            content=[
                *[dict(type="image", image=x) for x in images],
                dict(type="text", text=PROMPT + row["instruction"]),
            ],
        )
    ]
    prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    full = processor.apply_chat_template(
        [*messages, dict(role="assistant", content=[dict(type="text", text=str(row["action_id"]))])],
        tokenize=False,
    )
    x = processor(text=[prompt], images=images, return_tensors="pt")
    y = processor(text=[full], images=images, return_tensors="pt")
    n = x.input_ids.shape[1]
    assert torch.equal(x.input_ids, y.input_ids[:, :n])
    assert y.input_ids.shape[1] < 2048
    labels = y.input_ids.clone()
    labels[:, :n] = -100
    y["labels"] = labels
    return x, y


def fresh():
    torch.manual_seed(142)
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
    assert all(
        "lora_" in n and "text_model" in n for n, p in model.named_parameters() if p.requires_grad
    )
    return model


def predict(model, processor, rows, batches):
    model.eval()
    results = []
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        for row, (x, _) in zip(rows, batches, strict=True):
            generated = model.generate(
                **api.cuda(x), max_new_tokens=8, do_sample=False, use_cache=True
            )
            raw = processor.tokenizer.decode(
                generated[0, x.input_ids.shape[1] :], skip_special_tokens=True
            ).strip()
            results.append(
                dict(
                    id=row["id"],
                    target=row["action_id"],
                    raw=raw,
                    valid=raw in list("0123456789"),
                    exact=raw == str(row["action_id"]),
                )
            )
    return results


def metrics(outputs):
    classes = sorted({p["target"] for p in outputs})
    recall = {
        str(a): sum(p["exact"] for p in outputs if p["target"] == a)
        / sum(p["target"] == a for p in outputs)
        for a in classes
    }
    return dict(
        n=len(outputs),
        exact=sum(p["exact"] for p in outputs),
        invalid=sum(not p["valid"] for p in outputs),
        macro_recall=sum(recall.values()) / len(recall),
        per_class_recall=recall,
        majority_correct=max(sum(p["target"] == a for p in outputs) for a in classes),
    )


def evaluation_loss(model, batches):
    model.eval()
    values = []
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        for _, batch in batches:
            values.append(model(**api.cuda(batch)).loss.item())
    return sum(values) / len(values)


def fit(model, processor, rows, batches, steps, stage, report, start):
    groups = {
        a: [i for i, r in enumerate(rows) if r["action_id"] == a]
        for a in sorted({r["action_id"] for r in rows})
    }
    rng = random.Random(142)
    order = list(groups)
    rng.shuffle(order)
    parameters = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=2e-4)
    for step in range(steps):
        assert time.monotonic() - start < 3600, "One-hour local pilot cap"
        model.train()
        model.config.use_cache = False
        optimizer.zero_grad(set_to_none=True)
        losses = []
        ids = []
        # Rotate classes, shuffle each class cycle. Each effective batch mixes four actions.
        for micro in range(4):
            pos = (step * 4 + micro) % len(order)
            if pos == 0:
                rng.shuffle(order)
            index = rng.choice(groups[order[pos]])
            ids.append(rows[index]["id"])
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(**api.cuda(batches[index][1])).loss
            assert torch.isfinite(loss)
            (loss / 4).backward()
            losses.append(loss.item())
        norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0)
        assert torch.isfinite(norm) and norm > 0
        optimizer.step()
        entry = dict(
            stage=stage,
            step=step + 1,
            loss=sum(losses) / 4,
            ids=ids,
            elapsed_s=time.monotonic() - start,
        )
        with (OUT / "losses.jsonl").open("a") as f:
            f.write(json.dumps(entry) + "\n")
        report["status"] = stage
        report["updates"] = step + 1
        if (step + 1) % 10 == 0:
            write(report)
            print(json.dumps(entry), flush=True)
    model.save_pretrained(OUT / stage / "adapter")
    del optimizer


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    REPORT.mkdir(exist_ok=True)
    start = time.monotonic()
    report = dict(
        status="preflight",
        model=str(api.MODEL),
        contract="openfly_native_action_id_v1",
        quantization="BF16 Smol500; language-only LoRA r8",
        max_seconds=3600,
        aws_spend=0,
        official_evaluation_used=False,
        limitations="Offline next-action imitation only; new native-ID interface, not the FRD baseline. Causal history of three front frames at <=256px. No physical or simulator execution implied.",
    )
    try:
        index = ROOT / "index.jsonl"
        report["data_sha256"] = hashlib.sha256(index.read_bytes()).hexdigest()
        audit = json.loads((REPORT / "data_audit.json").read_text())
        assert audit["index_sha256"] == report["data_sha256"]
        rows = [json.loads(x) for x in index.read_text().splitlines()]
        train = [r for r in rows if r["split"] == "train"]
        dev = [r for r in rows if r["split"] == "dev"]
        classes = sorted({r["action_id"] for r in train})
        tiny = [next(r for r in train if r["action_id"] == a) for a in classes]
        report["overfit_ids"] = [r["id"] for r in tiny]
        report["train_rows"] = len(train)
        report["dev_rows"] = len(dev)
        torch.cuda.set_per_process_memory_fraction(0.70)
        processor = AutoProcessor.from_pretrained(
            str(api.MODEL),
            local_files_only=True,
            size={"longest_edge": 256},
            do_image_splitting=False,
        )
        tiny_batches = [encode(processor, r) for r in tiny]
        model = fresh()
        report["overfit_loss_before"] = evaluation_loss(model, tiny_batches)
        report["overfit_before"] = predict(model, processor, tiny, tiny_batches)
        write(report)
        fit(model, processor, tiny, tiny_batches, 80, "overfit", report, start)
        report["overfit_loss_after"] = evaluation_loss(model, tiny_batches)
        report["overfit_after"] = predict(model, processor, tiny, tiny_batches)
        report["overfit_pass"] = sum(p["exact"] for p in report["overfit_after"]) >= len(tiny) - 1
        write(report)
        del model
        gc.collect()
        torch.cuda.empty_cache()
        if not report["overfit_pass"]:
            report["status"] = "stopped_overfit_gate"
            return
        # Reset to identical base initialization: memorization weights never enter the pilot.
        model = fresh()
        train_batches = [encode(processor, r) for r in train]
        dev_batches = [encode(processor, r) for r in dev]
        report["pilot_eval_loss_before"] = dict(
            train=evaluation_loss(model, train_batches), dev=evaluation_loss(model, dev_batches)
        )
        report["dev_before"] = predict(model, processor, dev, dev_batches)
        write(report)
        fit(model, processor, train, train_batches, 160, "pilot", report, start)
        report["pilot_eval_loss_after"] = dict(
            train=evaluation_loss(model, train_batches), dev=evaluation_loss(model, dev_batches)
        )
        report["dev_after"] = predict(model, processor, dev, dev_batches)
        report["dev_blank_images"] = predict(
            model, processor, dev, [encode(processor, r, blank=True) for r in dev]
        )
        saved = report["dev_after"][:4]
        del model
        gc.collect()
        torch.cuda.empty_cache()
        model = PeftModel.from_pretrained(
            api.load_base(), str(OUT / "pilot/adapter"), is_trainable=False
        )
        report["reload_spots"] = predict(model, processor, dev[:4], dev_batches[:4])
        assert report["reload_spots"] == saved
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        raise
    finally:
        report["metrics"] = {
            key: metrics(report[key])
            for key in (
                "overfit_before",
                "overfit_after",
                "dev_before",
                "dev_after",
                "dev_blank_images",
            )
            if key in report
        }
        report["elapsed_s"] = time.monotonic() - start
        report["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        write(report)
        print(json.dumps(dict(status=report["status"], elapsed_s=report["elapsed_s"])), flush=True)


if __name__ == "__main__":
    main()
