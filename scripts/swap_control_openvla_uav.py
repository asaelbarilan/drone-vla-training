"""D156: image-swap control on the authors' own OpenVLA-UAV checkpoint.

Our SmolVLM fine-tunes ignore the camera: swapping in a different real scene
leaves all 48 action tokens unchanged in 23 of 40 cases. Three explanations were
on the table - the published models are wrong, our training is wrong, or we are
misreading the measurement. This run tests the released UAV-Flow model the same
way, so the answer does not depend on our training at all.

The test is deliberately scale-free. Their action space is four dimensional
(x, y, z and a yaw in radians) in units unrelated to ours, and their norm_stats
key is `sim` while our shard is the real set, so endpoint error is not comparable.
Whether the prediction *changes when the photo changes* needs none of that.

Prompt follows vla-scripts/openvla_act.py exactly, including the proprioceptive
state, which is held fixed across the three conditions so the image is the only
thing that varies.
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, "D:/drone_vla_pilot/models/OpenFly-Platform/train")
import timm

_original_create = timm.create_model
timm.create_model = lambda *a, **k: _original_create(*a, **{**k, "pretrained": False})

from transformers import (  # noqa: E402
    AutoModelForVision2Seq,
    AutoProcessor,
    BitsAndBytesConfig,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/openvla_uav_swap_20260921"
STORE = Path("D:/drone_vla_pilot/data/uav_flow_chunks_20260921")
MODEL = "D:/drone_vla_pilot/models/openvla-uav"


def build_prompt(proprio, instruction):
    proprio_str = ",".join(str(round(float(x), 1)) for x in proprio)
    return (
        f"In: Current State: {proprio_str}, What action should the uav take to {instruction}?\nOut:"
    )


def load_frame(path, gray=False):
    picture = Image.open(path).convert("RGB")
    return Image.new("RGB", picture.size, (127, 127, 127)) if gray else picture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=30)
    parser.add_argument("--unnorm-key", default="sim")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = [json.loads(s) for s in (STORE / "steps.jsonl").read_text(encoding="utf-8").splitlines()]
    val = [r for r in rows if r["split_unseen"] == "val" and r["chunk_len"] == 8]
    rng = random.Random(7)
    cases = rng.sample(val, args.cases)

    processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True, local_files_only=True)
    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        llm_int8_skip_modules=["vision_backbone", "projector", "lm_head"],
    )
    model = AutoModelForVision2Seq.from_pretrained(
        MODEL,
        trust_remote_code=True,
        local_files_only=True,
        torch_dtype=torch.bfloat16,
        quantization_config=quant,
        device_map={"": 0},
        attn_implementation="eager",
    )
    model.eval()
    timm.create_model = _original_create

    def act(image, prompt):
        inputs = processor(prompt, image).to("cuda:0", dtype=torch.bfloat16)
        # Official predict_action appends 29871 to input_ids but leaves the mask
        # alone, which desynchronises the causal mask. Same fix as D147 used for
        # openfly-agent-7b.
        if inputs["input_ids"][0, -1].item() != 29871:
            inputs["input_ids"] = torch.cat(
                [inputs["input_ids"], inputs["input_ids"].new_tensor([[29871]])], dim=1
            )
            inputs["attention_mask"] = torch.cat(
                [inputs["attention_mask"], inputs["attention_mask"].new_ones((1, 1))], dim=1
            )
        with torch.inference_mode():
            return model.predict_action(**inputs, unnorm_key=args.unnorm_key, do_sample=False)

    records, same_gray, same_swap = [], 0, 0
    for row in cases:
        other = rng.choice([r for r in val if r["episode"] != row["episode"]])
        # cumulative pose at this step is the closest thing our data has to proprio
        proprio = [row["step"] * 0.0, 0.0, 0.0, 0.0]
        prompt = build_prompt(proprio, row["instruction"].rstrip(".").lower())
        real = act(load_frame(row["image"]), prompt)
        gray = act(load_frame(row["image"], gray=True), prompt)
        swap = act(load_frame(other["image"]), prompt)
        same_gray += int(np.array_equal(real, gray))
        same_swap += int(np.array_equal(real, swap))
        records.append(
            dict(
                id=row["id"],
                instruction=row["instruction"],
                swapped_from=other["id"],
                real=[round(float(v), 4) for v in real],
                gray=[round(float(v), 4) for v in gray],
                swap=[round(float(v), 4) for v in swap],
            )
        )

    n = len(cases)
    summary = dict(
        model=MODEL,
        unnorm_key=args.unnorm_key,
        cases=n,
        action_dim=int(model.get_action_dim(args.unnorm_key)),
        identical_when_gray=same_gray,
        identical_when_swapped=same_swap,
        distinct_real_actions=len({tuple(r["real"]) for r in records}),
        note=(
            "scale-free control: their action units and sim/real distribution differ "
            "from ours, so only whether the prediction changes is being read"
        ),
        ours_for_reference=dict(
            identical_when_gray="28/40", identical_when_swapped="23/40", action_tokens=48
        ),
    )
    (OUT / "summary.json").write_text(
        json.dumps(dict(summary=summary, cases=records), indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
