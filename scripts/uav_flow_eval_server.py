"""D162: model server for UAV-Flow-Eval (UnrealZoo DowntownWest, closed loop).

Speaks the official protocol of OpenVLA-UAV/vla-scripts/openvla_act.py so the
unmodified batch_run_act_all.py drives it:

  POST /predict {image: base64 PNG 224x224, proprio: [x, y, z, yaw_deg], instr}
  -> {action: [[x, y, z, yaw_rad], ...]}   poses in the START frame, sim units
  POST /reset

Two models:

  openvla-uav  the released checkpoint, exactly the official server's maths
               (predict_action with unnorm_key "sim", rotate the step by the
               current yaw, add the current position and yaw). Deviation: NF4 on
               an 8 GB card instead of bf16 + flash-attention, plus the D156
               attention-mask fix for the appended 29871 token.
  qwen         our adapter (official format, K-step chunks, trained on REAL
               flights in metres). The simulator works in centimetres - the
               released model's "sim" action stats are ~10-50 per step - so the
               state is divided by 100 before it goes into our prompt and every
               predicted step is multiplied by 100. Each of the K steps is
               integrated in turn in the drone frame and returned as K poses,
               which the evaluator executes one after another.
"""

import argparse
import base64
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
from flask import Flask, jsonify, request
from PIL import Image

app = Flask(__name__)
STATE = {}


def openvla_loader(path):
    sys.path.insert(0, "D:/drone_vla_pilot/models/OpenFly-Platform/train")
    import timm

    original = timm.create_model
    timm.create_model = lambda *a, **k: original(*a, **{**k, "pretrained": False})
    from transformers import AutoModelForVision2Seq, AutoProcessor, BitsAndBytesConfig

    processor = AutoProcessor.from_pretrained(path, trust_remote_code=True, local_files_only=True)
    model = AutoModelForVision2Seq.from_pretrained(
        path,
        trust_remote_code=True,
        local_files_only=True,
        torch_dtype=torch.bfloat16,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            llm_int8_skip_modules=["vision_backbone", "projector", "lm_head"],
        ),
        device_map={"": 0},
        attn_implementation="eager",
    )
    model.eval()
    timm.create_model = original

    def predict(image, proprio, instruction):
        state = ",".join(str(round(float(x), 1)) for x in proprio)
        prompt = (
            f"In: Current State: {state}, What action should the uav take to {instruction}?\nOut:"
        )
        inputs = processor(prompt, image).to("cuda:0", dtype=torch.bfloat16)
        if inputs["input_ids"][0, -1].item() != 29871:
            inputs["input_ids"] = torch.cat(
                [inputs["input_ids"], inputs["input_ids"].new_tensor([[29871]])], dim=1
            )
            inputs["attention_mask"] = torch.cat(
                [inputs["attention_mask"], inputs["attention_mask"].new_ones((1, 1))], dim=1
            )
        with torch.inference_mode():
            step = model.predict_action(**inputs, unnorm_key="sim", do_sample=False)
        return [np.asarray(step, dtype=float)]  # one step, sim units

    return predict


def qwen_loader(adapter, chunk, precision):
    from peft import PeftModel
    from train_uav_flow_vla import OFFICIAL_PROMPT, encode, official_stats, setup
    from uav_flow_action_tokenizer import ActionTokenizer

    api, processor, base, _ = setup("qwen", precision)
    tokenizer = ActionTokenizer(processor.tokenizer, official_stats())
    model = PeftModel.from_pretrained(base, adapter)
    model.eval()

    def predict(image, proprio, instruction):
        metres = [proprio[0] / 100, proprio[1] / 100, proprio[2] / 100, proprio[3]]
        state = ",".join(str(round(float(x), 1)) for x in metres)
        row = dict(prompt=OFFICIAL_PROMPT.format(state=state, instruction=instruction))
        batch = encode(processor, tokenizer, row, chunk, with_answer=False, image=image)
        with torch.inference_mode():
            out = model.generate(
                **api.cuda(batch), max_new_tokens=4 * chunk + 2, do_sample=False, use_cache=True
            )
        steps = tokenizer.decode(out[0, batch["input_ids"].shape[1] :].tolist(), chunk)
        if steps is None:
            return []
        return [np.array([dx * 100, dy * 100, dz * 100, dyaw]) for dx, dy, dz, dyaw in steps]

    return predict


@app.route("/reset", methods=["POST"])
def reset():
    return jsonify({"status": "ok"})


@app.route("/predict", methods=["POST"])
def predict():
    data = request.json
    image = Image.open(io.BytesIO(base64.b64decode(data["image"]))).convert("RGB")
    proprio = np.array(data["proprio"], dtype=float)  # x, y, z (sim units), yaw (deg)
    steps = STATE["predict"](image, proprio, data["instr"])
    poses, position, yaw = [], proprio[:3].copy(), math.radians(proprio[3])
    for step in steps:
        c, s = math.cos(yaw), math.sin(yaw)
        position = position + np.array(
            [c * step[0] - s * step[1], s * step[0] + c * step[1], step[2]]
        )
        yaw = yaw + float(step[3])
        poses.append([*position.tolist(), yaw])
    STATE["log"].write(
        json.dumps(dict(instr=data["instr"], proprio=proprio.tolist(), poses=poses)) + "\n"
    )
    STATE["log"].flush()
    return jsonify({"status": "success", "action": poses})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["openvla-uav", "qwen"])
    parser.add_argument("--path", default="D:/drone_vla_pilot/models/openvla-uav")
    parser.add_argument("--chunk", type=int, default=8)
    parser.add_argument("--precision", default="nf4", choices=["nf4", "bf16"])
    parser.add_argument("--port", type=int, default=5007)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    if args.model == "openvla-uav":
        STATE["predict"] = openvla_loader(args.path)
    else:
        STATE["predict"] = qwen_loader(args.path, args.chunk, args.precision)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    STATE["log"] = open(args.log, "a", encoding="utf-8")  # noqa: SIM115 - lives with the server
    app.run(host="127.0.0.1", port=args.port, threaded=False)


if __name__ == "__main__":
    main()
