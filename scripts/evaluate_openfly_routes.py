# ruff: noqa: E402
"""D148 frozen route and original-RLDS interface diagnostics; no training."""

import os

for key in ("HF_HOME", "TORCH_HOME"):
    os.environ[key] = "D:/drone_vla_pilot/hf_cache"
os.environ["USE_TF"] = "0"
os.environ["HF_HUB_OFFLINE"] = "1"
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--limit", type=int, default=2)
parser.add_argument("--eval-data", type=Path)
parser.add_argument("--prompt-style", choices=("model_card", "training"), default="model_card")
parser.add_argument("--history-pooling", choices=("released", "training"), default="released")
parser.add_argument("--norm-key", required=True)
parser.add_argument("--precision", choices=("nf4", "bf16_offload"), default="nf4")
args = parser.parse_args()
assert args.eval_data is not None
args.out.mkdir(parents=True, exist_ok=False)
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
from uavlab.training.openfly_codec import OpenFlyCodec

codec = OpenFlyCodec(json.loads((root / "config.json").read_text()), args.norm_key)
coverage = codec.require_coverage([0, 1, 2, 3, 4, 5, 8, 9])
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
    quantization_config=quant if args.precision == "nf4" else None,
    max_memory={0: "5500MiB", "cpu": "12GiB"} if args.precision == "bf16_offload" else None,
    device_map={"": 0} if args.precision == "nf4" else "auto",
    attn_implementation="eager",
    local_files_only=True,
    output_loading_info=True,
)
timm.create_model = original_create
info = {k: sorted(v) if isinstance(v, set) else v for k, v in info.items()}
(args.out / "loading.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
assert not info["missing_keys"] and not info["unexpected_keys"], info
model.eval()
released_forward = model.vision_backbone.forward
if True:
    import types

    def training_pooling(self, pixel_values, grid_size=16):
        result = []
        for i in range(3):
            dino, siglip = torch.split(pixel_values[i : i + 1], [3, 3], dim=1)
            dino = self.featurizer(dino)[0]
            siglip = self.fused_featurizer(siglip)[0]
            if i < 2:
                dino = self.post_process(dino, grid_size)
                siglip = self.post_process(siglip, grid_size)
            result.append(torch.cat([dino, siglip], dim=2))
        return result

    training_forward = types.MethodType(training_pooling, model.vision_backbone)
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
if args.eval_data:
    rows = [json.loads(line) for line in args.eval_data.read_text().splitlines()]
    rows = [dict(r, decision_id=r["id"]) for r in rows]
outputs = []
original_generate = model.generate
last_tokens = []
new_token_count = []


def capture_generate(*a, **kw):
    input_length = (a[0] if a else kw["input_ids"]).shape[-1]
    result = original_generate(*a, **kw)
    new_token_count[:] = [result.shape[-1] - input_length]
    last_tokens[:] = result[0, -model.get_action_dim(args.norm_key) :].tolist()
    return result


model.generate = capture_generate
for r in rows:
    row_norm_key = r.get("norm_key", args.norm_key)
    codec = OpenFlyCodec(json.loads((root / "config.json").read_text()), row_norm_key)
    model.vision_backbone.forward = (
        training_forward
        if r.get("history_pooling", args.history_pooling) == "training"
        else released_forward
    )
    assert time.monotonic() - start < 1800
    if args.eval_data:
        image_paths = [Path(x) for x in r["images"]]
        assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in image_paths] == r[
            "image_sha256"
        ]
    else:
        image_paths = [Path(r["data_root"]) / r["images"]["front"]] * 3
    image_path = image_paths[-1]
    images = [Image.open(p).convert("RGB") for p in image_paths]
    edge = r.get("max_image_edge", 256)
    if edge:
        for image in images:
            image.thumbnail((edge, edge))
    if r.get("image_control") == "gray":
        images = [Image.new("RGB", im.size, (127, 127, 127)) for im in images]
    prompt = r["instruction"]
    if r.get("prompt_style", args.prompt_style) == "training":
        builder = LLaMa2ChatPromptBuilder("prismatic")
        builder.add_turn("human", f"What action should the robot take to {prompt.lower()}?")
        prompt = builder.get_prompt()
    inputs = processor(prompt, images).to("cuda:0", dtype=torch.bfloat16)
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
        action = model.predict_action(**inputs, unnorm_key=row_norm_key, do_sample=False)
    assert new_token_count[0] == 8, "Early EOS: reject input-token slicing"
    torch.cuda.synchronize()
    outputs.append(
        dict(
            decision_id=r["decision_id"],
            instruction=r["instruction"],
            variant=r.get("variant"),
            norm_key=row_norm_key,
            prompt_style=r.get("prompt_style", args.prompt_style),
            history_pooling=r.get("history_pooling", args.history_pooling),
            max_image_edge=edge,
            image_indices=r.get("image_indices"),
            prompt=prompt,
            image=str(image_path),
            initial_history=(
                "see frozen input variant and indices; original RLDS diagnostics "
                "may contain flagged future frames"
            )
            if args.eval_data
            else "three copies of initial front image",
            images=[str(p) for p in image_paths],
            image_sha256=r["image_sha256"],
            raw_action=action.tolist(),
            strict_decoded=codec.decode(last_tokens),
            image_control=r.get("image_control", "original"),
            action_token_ids=list(last_tokens),
            generated_token_count=new_token_count[0],
            tokens_in_action_range=all(
                1 <= model.vocab_size - t <= len(model.bins) for t in last_tokens
            ),
            rounded_action=action.round().astype(int).tolist(),
            latency_s=time.monotonic() - before,
        )
    )
    with (args.out / "predictions.jsonl").open("a") as stream:
        stream.write(json.dumps(outputs[-1]) + "\n")
    print(json.dumps({"completed": len(outputs), "total": len(rows)}), flush=True)
report = dict(
    status="inference_complete",
    quantization="NF4 language linear layers; BF16 vision/projector"
    if args.precision == "nf4"
    else "unquantized BF16 with CPU offload",
    device_map={str(k): str(v) for k, v in model.hf_device_map.items()},
    norm_key=args.norm_key,
    coverage=coverage,
    calibration_status="vertical-capable published profile; historical context mapping unresolved",
    prompt_style=args.prompt_style,
    history_pooling=args.history_pooling,
    outputs=outputs,
    loading=info,
    peak_allocated_bytes=torch.cuda.max_memory_allocated(),
    elapsed_s=time.monotonic() - start,
    flight_comparison_complete=False,
    evaluation_data=str(args.eval_data) if args.eval_data else None,
    evaluation_data_sha256=hashlib.sha256(args.eval_data.read_bytes()).hexdigest()
    if args.eval_data
    else None,
)
(args.out / "probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
