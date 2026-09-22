"""D157: does a PyTorch-trained action adapter survive the move to llama.cpp?

The deployment target is one Qwen3-VL-4B base in llama.cpp serving both the VLM
and the VLA, with the action LoRA switched on per request. Three things have to
hold for that to be real, and this script tests them against a running server:

  1. the adapter loads alongside the vision projector,
  2. switching its scale per request changes the output (scale 0 behaves as the
     plain VLM, scale 1 emits action tokens),
  3. the action tokens decode to the same actions PyTorch produced from the same
     adapter - despite the base being Q4_K_M here and NF4 in training.

Point 3 is only answerable after the PyTorch reference is run with the server
stopped, since both do not fit on the card at once; this script records the
llama.cpp side and the comparison runs separately.

Prompt caching is disabled on every request. A cache built under one adapter
scale is not valid under another, and silently reusing it would corrupt exactly
the comparison being made.
"""

import base64
import json
import random
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = Path("D:/drone_vla_pilot/data/uav_flow_chunks_20260921")
OUT = ROOT / "reports/vla_llamacpp_chain_20260921"
SERVER = "http://127.0.0.1:8790"
PROMPT = "Drone forward camera. What action should the drone take to {instruction}?"
CASES = 20


def post(path, body):
    request = urllib.request.Request(
        SERVER + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(request, timeout=300).read())


def cases():
    rows = [json.loads(s) for s in (STORE / "steps.jsonl").read_text(encoding="utf-8").splitlines()]
    val = [r for r in rows if r["split_unseen"] == "val" and r["chunk_len"] == 8]
    return random.Random(157).sample(val, CASES)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    props = json.loads(urllib.request.urlopen(SERVER + "/props", timeout=30).read())
    marker = props["media_marker"]
    assert props["modalities"]["vision"], "server has no vision capability"

    records = []
    for row in cases():
        text = PROMPT.format(instruction=row["instruction"].rstrip(".").lower())
        image = base64.b64encode(Path(row["image"]).read_bytes()).decode()
        templated = post(
            "/apply-template",
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/jpeg;base64," + image},
                            },
                            {"type": "text", "text": text},
                        ],
                    }
                ]
            },
        )["prompt"]
        assert templated.count(marker) == 1, "expected exactly one media marker"
        result = {}
        for scale in (1.0, 0.0):
            out = post(
                "/completion",
                {
                    "prompt": {"prompt_string": templated, "multimodal_data": [image]},
                    "n_predict": 49,
                    "temperature": 0,
                    "top_k": 1,
                    "return_tokens": True,
                    "cache_prompt": False,
                    "lora": [{"id": 0, "scale": scale}],
                },
            )
            result[f"scale_{scale:g}"] = dict(
                tokens=out.get("tokens", []), text=out.get("content", "")
            )
        records.append(
            dict(id=row["id"], instruction=row["instruction"], image=row["image"], **result)
        )
        print(json.dumps(dict(done=len(records), total=CASES)), flush=True)

    name = sys.argv[1] if len(sys.argv) > 1 else "llamacpp_outputs.json"
    (OUT / name).write_text(
        json.dumps(dict(server=SERVER, build=props.get("build_info"), records=records), indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    sys.exit(main())
