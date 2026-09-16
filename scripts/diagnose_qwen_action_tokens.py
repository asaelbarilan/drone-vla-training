"""Training-only per-token diagnosis of the preserved FLU pilot checkpoint."""

import json
import re
from pathlib import Path

import torch
from peft import PeftModel
from run_qwen_direct_vla_overfit import MODEL, cuda, encode, load_base, subset
from transformers import AutoProcessor

root = Path("D:/drone_vla_pilot/data/public_goal_fixture_20260916_v1")
rows = subset([json.loads(x) for x in (root / "index.jsonl").read_text().splitlines()])
processor = AutoProcessor.from_pretrained(str(MODEL), local_files_only=True)
torch.cuda.set_per_process_memory_fraction(0.70)
model = PeftModel.from_pretrained(
    load_base(), "D:/drone_vla_pilot/runs/qwen_overfit_20260916_c/adapter", is_trainable=False
).eval()
results = []
for row in rows:
    _, batch = encode(processor, root, row)
    labels = batch["labels"][0, 1:]
    positions = torch.where(labels != -100)[0]
    expected = labels[positions]
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        inputs = cuda({k: v for k, v in batch.items() if k != "labels"})
        logits = model(**inputs, use_cache=False).logits[0, positions.to("cuda"), :].float()
        logprob = logits.log_softmax(-1)
        nll = -logprob.gather(1, expected.to("cuda")[:, None]).squeeze(1).cpu()
        guessed = logits.argmax(-1).cpu()
    tokens = []
    for token_id, guess, value in zip(
        expected.tolist(), guessed.tolist(), nll.tolist(), strict=True
    ):
        token = processor.tokenizer.decode([token_id])
        kind = (
            "boolean"
            if token in ("true", "false")
            else "number"
            if re.fullmatch(r"\d+", token)
            else "format"
        )
        tokens.append(
            {
                "token": token,
                "kind": kind,
                "nll": value,
                "top_token": processor.tokenizer.decode([guess]),
                "correct": token_id == guess,
            }
        )
    results.append({"decision_id": row["decision_id"], "target": row["target"], "tokens": tokens})
summary = {}
for kind in ("format", "number", "boolean"):
    selected = [t for r in results for t in r["tokens"] if t["kind"] == kind]
    summary[kind] = {
        "tokens": len(selected),
        "mean_nll": sum(t["nll"] for t in selected) / len(selected),
        "top1_correct": sum(t["correct"] for t in selected),
    }
report = {
    "source": "old FLU adapter c; TRAIN subset only",
    "teacher_forced_not_generation": True,
    "summary": summary,
    "examples": results,
}
Path("reports/vla_frd_followup_20260916/token_diagnosis.json").write_text(
    json.dumps(report, indent=2)
)
print(json.dumps(summary, indent=2))
