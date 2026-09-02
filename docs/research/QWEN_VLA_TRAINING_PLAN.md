# Qwen3-VL direct-flight training plan

Decision date: 2026-08-31. Scope: local deterministic simulator first.

## Decision

Train the direct VLA with supervised fine-tuning (behavior cloning) first, then
use DAgger-style data aggregation if closed-loop failures show distribution
shift. Do not begin with GRPO. GRPO is optional only after the SFT/DAgger policy
is competent and a deterministic reward has been validated.

This keeps the backbone family fixed: the comparison uses Qwen3-VL 4B; C8 adds
only a task-specific LoRA action adapter. Report both the frozen zero-shot C8
and the adapted C8 so the effect of training is explicit.

## Implemented data contract

- Teacher: C0 oracle, privileged only during labelling.
- Student input: synchronized front RGB, downward RGB, mission text, and the
  declared coarse goal-direction bucket. No coordinates, depth, or simulator
  truth are serialized into the student input.
- Student output: the released AeroVLA 99-bin forward/vertical/yaw JSON action
  plus `land`.
- Split unit: entire deterministic scene seed. Seeds 1-40 remain held out;
  collection is restricted to 1000-1999.
- Prompt construction is shared by collection and deployment to prevent
  train/inference drift.
- Both official Qwen `conversations` JSONL and native ms-swift
  `messages`/`images` JSONL are generated.

## Commands

```powershell
uavlab collect-qwen-vla --episodes 200 --start-seed 1000 --stride 10 --out data/qwen_vla_sft
uavlab validate-qwen-vla --data data/qwen_vla_sft
powershell -ExecutionPolicy Bypass -File scripts/train_qwen_vla_sft.ps1
```

The executable training recipe is QLoRA SFT with NF4 4-bit loading, rank-8
LoRA, a frozen vision encoder/aligner, batch size 1, gradient accumulation 16,
and 224-pixel mosaics capped at 64 visual tokens.

## Gates

1. Data: at least 100 successful episodes and 10,000 samples; train/validation
   seeds disjoint; at least one LAND positive; all targets strictly parse.
2. Offline: strict JSON parse rate >=99.5%; LAND precision >=95% and recall
   >=90% on a terminal-balanced set; no single action dominates by collapse.
3. Closed loop: at least 3/5 development seeds before DAgger, then 4/5 before
   held-out evaluation.
4. DAgger: collect student-visited states with the same C0 teacher, retrain by
   SFT, and repeat two or three times. Suggested teacher execution mixture:
   0.5, 0.25, then 0.
5. GRPO: consider only if SFT/DAgger clears 3/5 but plateaus and reward
   attribution is stable. It is not a repair for a policy that cannot yet emit
   valid actions or reach goals.

## Current resource blocker

The laptop has an RTX 4060 Laptop GPU with 8 GB VRAM and approximately 3.5 GB
free disk. The installed 4.14 GB Qwen AWQ checkpoint is an inference artifact;
this recipe intentionally starts from the BF16 base and quantizes with
bitsandbytes NF4 for QLoRA. Free or move at least 15-20 GB before downloading
the base, storing data, and writing adapters. Even then, Qwen3-VL 4B training on
8 GB is not guaranteed; use a larger GPU or fall back to Qwen3-VL 2B if it
cannot fit. The official dense 4B LoRA example reports 2 x 21 GiB before QLoRA.

## Evidence

The broader 31-work evidence ledger is `docs/research/spf_evidence.json` and
passes the project validator (31 meaningful works, 27 primary sources). The
training decision additionally follows:

- Official Qwen3-VL fine-tuning documentation: single-image conversation
  format, LoRA, and strict image-token matching.
- Official ms-swift Qwen3-VL guide: custom train/validation JSONL, frozen ViT
  and aligner, and Qwen3-VL 4B LoRA settings.
- Official ms-swift QLoRA recipe: bitsandbytes NF4, double quantization, and
  rank-8 LoRA.
- DAgger (Ross et al., 2011): aggregate expert labels on states induced by the
  learned policy to address sequential covariate shift.
- MobileVLA-R1 and SimpleVLA-RL: their RL stages start from supervised models;
  SimpleVLA-RL explicitly requires an SFT VLA and parallel rollout machinery.

Primary links:

- https://github.com/QwenLM/Qwen3-VL/tree/main/qwen-vl-finetune
- https://github.com/modelscope/ms-swift/blob/main/docs/source_en/BestPractices/Qwen3-VL-Best-Practice.md
- https://github.com/modelscope/ms-swift/blob/main/examples/train/qlora/bnb/train.sh
- https://proceedings.mlr.press/v15/ross11a.html
- https://github.com/AIGeeksGroup/MobileVLA-R1
- https://github.com/PRIME-RL/SimpleVLA-RL
