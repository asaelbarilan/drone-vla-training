"""D148 unchanged Qwen adapter on all decisions of three frozen routes."""

import argparse
import hashlib
import importlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
import torch
from peft import PeftModel
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["smol256", "smol500", "qwen"])
    parser.add_argument("--aligned-panel", action="store_true")
    args = parser.parse_args()
    out = Path("reports/vla_openfly_routes_20260919")
    source = Path("reports/vla_openfly_repair_20260918/rerun_inputs.jsonl")
    originals = {r["id"]: r for r in map(json.loads, source.read_text().splitlines())}
    subset = [
        r
        for r in map(json.loads, (out / "route_inputs.jsonl").read_text().splitlines())
        if r["variant"] == "prior_adjacent"
    ]
    api = importlib.import_module(
        "run_qwen_frd_overfit" if args.model == "qwen" else "run_smol_frd_overfit"
    )
    if args.model == "smol500":
        api.MODEL = Path(
            "D:/drone_vla_pilot/models/SmolVLM-500M-Instruct/a7da5b986cb59b408707209984f360a5f4ad7e47"
        )
    processor = api.AutoProcessor.from_pretrained(
        str(api.MODEL),
        local_files_only=True,
        **(
            {}
            if args.model == "qwen"
            else {"size": {"longest_edge": 256}, "do_image_splitting": False}
        ),
    )
    torch.cuda.set_per_process_memory_fraction(0.70)
    model = api.load_base()
    model = PeftModel.from_pretrained(
        model, f"D:/drone_vla_pilot/runs/{args.model}_joint_20260917_a/adapter_s400"
    )
    model.eval()
    reference = next(iter(originals.values()))["prompt"].split("Route: ")[0]
    outputs = []
    start = time.monotonic()
    for row in subset:
        assert time.monotonic() - start < 1800
        images = []
        for name, sha in zip(row["images"], row["image_sha256"], strict=True):
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha
            im = Image.open(name).convert("RGB")
            im.thumbnail((256, 256))
            if row.get("image_control") == "gray":
                im = Image.new("RGB", im.size, (127, 127, 127))
            images.append(im)
        prompt = reference + "Route: " + row["instruction"]
        content = [{"type": "image", "image": im} for im in images] + [
            {"type": "text", "text": prompt}
        ]
        text = processor.apply_chat_template(
            [{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True
        )
        inputs = processor(text=[text], images=images, return_tensors="pt")
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            tokens = model.generate(
                **api.cuda(inputs), max_new_tokens=12, do_sample=False, use_cache=True
            )
        raw = processor.tokenizer.decode(
            tokens[0, inputs.input_ids.shape[1] :], skip_special_tokens=True
        )
        parsed = int(raw.strip()) if raw.strip() in set("012345") else None
        outputs.append(
            dict(
                id=row["id"],
                raw=raw,
                action_id=parsed,
                prompt=prompt,
                image_sha256=row["image_sha256"],
                image_control=row.get("image_control", "original"),
            )
        )
        print(
            json.dumps(dict(model=args.model, completed=len(outputs), total=len(subset))),
            flush=True,
        )
    (out / (args.model + "_routes.json")).write_text(
        json.dumps(
            dict(
                model=args.model,
                status="complete",
                elapsed_s=time.monotonic() - start,
                outputs=outputs,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
