# ruff: noqa: E402
"""Bounded local OpenFly 4-bit inference; raw outputs are not flight commands."""

import os

for key in ("HF_HOME", "TORCH_HOME"):
    os.environ[key] = "D:/drone_vla_pilot/hf_cache"
os.environ["USE_TF"] = "0"
os.environ["HF_HUB_OFFLINE"] = "1"
import argparse
import json
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--limit", type=int, default=2)
parser.add_argument("--prompt-style", choices=("model_card", "training"), default="model_card")
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, "D:/drone_vla_pilot/models/OpenFly-Platform/train")
import timm
import torch
from extern.hf.configuration_prismatic import OpenFlyConfig
from extern.hf.modeling_prismatic import OpenVLAForActionPrediction
from extern.hf.processing_prismatic import PrismaticImageProcessor, PrismaticProcessor
from model.prompt_llama2 import LLaMa2ChatPromptBuilder
from PIL import Image
from transformers import BitsAndBytesConfig, LlamaTokenizerFast

root = Path("D:/drone_vla_pilot/models/openfly-agent-7b")
# The complete checkpoint includes both vision encoders. Avoid downloading and
# initializing redundant standalone encoder weights; require no missing keys.
original_create = timm.create_model


def create_from_checkpoint(*a, **kw):
    kw["pretrained"] = False
    return original_create(*a, **kw)


timm.create_model = create_from_checkpoint
torch.cuda.set_per_process_memory_fraction(0.80)
start = time.monotonic()
config = OpenFlyConfig.from_pretrained(root, local_files_only=True)
quant = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
    llm_int8_skip_modules=["vision_backbone", "projector", "lm_head"],
)
model, info = OpenVLAForActionPrediction.from_pretrained(
    root,
    config=config,
    torch_dtype=torch.bfloat16,
    quantization_config=quant,
    device_map={"": 0},
    attn_implementation="eager",
    local_files_only=True,
    output_loading_info=True,
)
timm.create_model = original_create
info = {k: sorted(v) if isinstance(v, set) else v for k, v in info.items()}
(args.out / "loading.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
assert not info["missing_keys"] and not info["unexpected_keys"], info
model.eval()
print("MODEL_LOADED", time.monotonic() - start, flush=True)
tokenizer = LlamaTokenizerFast.from_pretrained(root, local_files_only=True)
processor = PrismaticProcessor(PrismaticImageProcessor.from_pretrained(root), tokenizer)
rows = [
    json.loads(s)
    for s in Path("D:/drone_vla_pilot/data/local_expanded_20260917_v4/index.jsonl")
    .read_text()
    .splitlines()
]
rows = [
    r
    for r in rows
    if r["split"] == "val" and r["task_group"] == "visual" and r["seed"] in (1410, 1415)
][: args.limit]
outputs = []
original_generate = model.generate
last_tokens = []


def capture_generate(*a, **kw):
    result = original_generate(*a, **kw)
    last_tokens[:] = result[0, -model.get_action_dim("vln_norm") :].tolist()
    return result


model.generate = capture_generate
for r in rows:
    image_path = Path(r["data_root"]) / r["images"]["front"]
    image = Image.open(image_path).convert("RGB")
    prompt = r["instruction"]
    if args.prompt_style == "training":
        builder = LLaMa2ChatPromptBuilder("prismatic")
        builder.add_turn("human", f"What action should the robot take to {prompt.lower()}?")
        prompt = builder.get_prompt()
    inputs = processor(prompt, [image, image, image]).to("cuda:0", dtype=torch.bfloat16)
    # Official predict_action appends 29871 but leaves attention_mask unchanged.
    # Append both here so unpadded prompt and mask stay aligned.
    if inputs["input_ids"][0, -1].item() != 29871:
        inputs["input_ids"] = torch.cat(
            [inputs["input_ids"], inputs["input_ids"].new_tensor([[29871]])], dim=1
        )
        inputs["attention_mask"] = torch.cat(
            [inputs["attention_mask"], inputs["attention_mask"].new_ones((1, 1))], dim=1
        )
    torch.cuda.synchronize()
    before = time.monotonic()
    with torch.inference_mode():
        action = model.predict_action(**inputs, unnorm_key="vln_norm", do_sample=False)
    torch.cuda.synchronize()
    outputs.append(
        dict(
            decision_id=r["decision_id"],
            instruction=r["instruction"],
            prompt=prompt,
            image=str(image_path),
            initial_history="three copies of initial front image",
            raw_action=action.tolist(),
            action_token_ids=list(last_tokens),
            tokens_in_action_range=all(
                1 <= model.vocab_size - t <= len(model.bins) for t in last_tokens
            ),
            rounded_action=action.round().astype(int).tolist(),
            latency_s=time.monotonic() - before,
        )
    )
    print(json.dumps(outputs[-1]), flush=True)
report = dict(
    status="inference_complete",
    quantization="NF4 language linear layers; BF16 vision/projector",
    norm_key="vln_norm",
    prompt_style=args.prompt_style,
    outputs=outputs,
    loading=info,
    peak_allocated_bytes=torch.cuda.max_memory_allocated(),
    elapsed_s=time.monotonic() - start,
    flight_comparison_complete=False,
)
(args.out / "probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
