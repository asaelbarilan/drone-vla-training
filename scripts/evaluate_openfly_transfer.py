"""Evaluate saved local FRD adapters on official OpenFly images without training."""

import argparse
import hashlib
import importlib
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from PIL import Image

from uavlab.training.direct_vla_frd import parse_target, student_prompt, target_json

p = argparse.ArgumentParser()
p.add_argument("--model", choices=["smol256", "smol500", "qwen"], required=True)
p.add_argument("--adapter", type=Path, required=True)
p.add_argument(
    "--data", type=Path, default=Path("D:/drone_vla_pilot/data/openfly_eval_20260917/eval.jsonl")
)
p.add_argument("--out", type=Path, required=True)
args = p.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
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
torch.cuda.set_per_process_memory_fraction(0.70)
model = PeftModel.from_pretrained(api.load_base(), str(args.adapter), is_trainable=False).eval()
rows = [json.loads(line) for line in args.data.read_text().splitlines()]
outputs = []
start = time.monotonic()
for row in rows:
    assert time.monotonic() - start < 1800
    image_path = Path(row["images"][-1])
    assert hashlib.sha256(image_path.read_bytes()).hexdigest() == row["image_sha256"][-1]
    image = Image.open(image_path).convert("RGB")
    prompt = student_prompt(row["instruction"], {})
    prompt = prompt.replace(
        "Image: front RGB above downward RGB.",
        "Image: current front RGB only; no downward camera is available.",
    )
    prompt = prompt.replace(
        "Use only the instruction, image and supplied odometry.",
        "Use only the instruction and image.",
    )
    prompt = prompt.replace(
        "Odometry: {}", "Odometry: unavailable; do not assume zero position or velocity."
    )
    messages = [
        dict(role="user", content=[dict(type="image", image=image), dict(type="text", text=prompt)])
    ]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[image], return_tensors="pt")
    before = time.monotonic()
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        generated = model.generate(
            **api.cuda(inputs), max_new_tokens=80, do_sample=False, use_cache=True
        )
    torch.cuda.synchronize()
    raw = processor.tokenizer.decode(
        generated[0, inputs.input_ids.shape[1] :], skip_special_tokens=True
    )
    try:
        parsed = json.loads(target_json(parse_target(raw)))
        valid = True
    except (ValueError, TypeError, KeyError):
        parsed = None
        valid = False
    output = dict(
        id=row["id"],
        prompt=prompt,
        image=str(image_path),
        image_sha256=row["image_sha256"][-1],
        raw=raw,
        parsed=parsed,
        valid=valid,
        latency_s=time.monotonic() - before,
    )
    outputs.append(output)
    with (args.out / "predictions.jsonl").open("a") as f:
        f.write(json.dumps(output) + "\n")
    print(json.dumps(dict(model=args.model, completed=len(outputs), total=len(rows))), flush=True)
report = dict(
    status="complete",
    model=args.model,
    base=str(api.MODEL),
    adapter=str(args.adapter),
    adapter_sha256=hashlib.file_digest(
        (args.adapter / "adapter_model.safetensors").open("rb"), "sha256"
    ).hexdigest(),
    data_sha256=hashlib.sha256(args.data.read_bytes()).hexdigest(),
    outputs=outputs,
    missing_inputs=["downward_camera", "velocity", "verified_ENU_odometry"],
    observation_protocol="current front image only; no invented state or future frames",
    wall_seconds=time.monotonic() - start,
    peak_allocated_bytes=torch.cuda.max_memory_allocated(),
    closed_loop_flights=False,
)
(args.out / "report.json").write_text(json.dumps(report, indent=2))
