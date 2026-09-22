"""D157: PyTorch reference for the llama.cpp chain test, and the comparison.

Runs the same adapter on the same 20 held-out frames the way it was trained -
Qwen3-VL-4B at NF4 in PyTorch - and compares against what llama.cpp produced on a
Q4_K_M base. The quantisations differ, so identical tokens are not expected. What
matters is whether the decoded actions agree closely, measured against how far
apart predictions for *different* frames are: a deployment gap much smaller than
the between-frame spread means the adapter carries over; a gap of the same size
means llama.cpp is effectively producing different actions.
"""

import json
import sys

import numpy as np
import torch
from chain_test_llamacpp import OUT, cases
from peft import PeftModel
from train_uav_flow_vla import encode, setup
from uav_flow_action_tokenizer import ActionTokenizer, load_stats

ADAPTER = "D:/drone_vla_pilot/runs/qwen_chain_test/adapter_s60"


def main():
    api, processor, base, _ = setup("qwen")
    globals()["api"] = api
    tokenizer = ActionTokenizer(processor.tokenizer, load_stats("split_unseen"))
    model = PeftModel.from_pretrained(base, ADAPTER)
    model.eval()

    llama = {
        r["id"]: r
        for r in json.loads((OUT / "llamacpp_outputs.json").read_text(encoding="utf-8"))["records"]
    }
    rows, torch_tokens = cases(), {}
    for row in rows:
        batch = encode(processor, tokenizer, row, 8, with_answer=False)
        with torch.inference_mode():
            out = model.generate(**api.cuda(batch), max_new_tokens=49, do_sample=False)
        torch_tokens[row["id"]] = out[0, batch["input_ids"].shape[1] :].tolist()

    agree, gaps, chunks_t, chunks_l = [], [], [], []
    for row in rows:
        t_ids, l_ids = torch_tokens[row["id"]], llama[row["id"]]["scale_1"]["tokens"]
        t_act = [i for i in t_ids if tokenizer.is_action_token(i)][:48]
        l_act = [i for i in l_ids if tokenizer.is_action_token(i)][:48]
        agree.append(sum(a == b for a, b in zip(t_act, l_act, strict=False)) / 48)
        ct, cl = tokenizer.decode(t_act, 8), tokenizer.decode(l_act, 8)
        if ct is None or cl is None:
            continue
        chunks_t.append(ct[:, :3].sum(axis=0))
        chunks_l.append(cl[:, :3].sum(axis=0))
        gaps.append(float(np.linalg.norm(chunks_t[-1] - chunks_l[-1])))

    t = np.array(chunks_t)
    spread = [
        float(np.linalg.norm(t[i] - t[j])) for i in range(len(t)) for j in range(i + 1, len(t))
    ]
    summary = dict(
        cases=len(rows),
        compared_chunks=len(gaps),
        token_agreement_median=round(float(np.median(agree)), 3),
        token_agreement_min=round(float(np.min(agree)), 3),
        deployment_gap_m=dict(
            median=round(float(np.median(gaps)), 4), max=round(float(np.max(gaps)), 4)
        ),
        between_frame_spread_m=dict(median=round(float(np.median(spread)), 4)),
        ratio_gap_to_spread=round(float(np.median(gaps)) / float(np.median(spread)), 3),
        bases=dict(pytorch="Qwen3-VL-4B-Instruct NF4", llamacpp="Qwen3VL-4B-Instruct Q4_K_M"),
        adapter=ADAPTER,
    )
    (OUT / "comparison.json").write_text(
        json.dumps(dict(summary=summary, torch_tokens=torch_tokens), indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    sys.exit(main())
