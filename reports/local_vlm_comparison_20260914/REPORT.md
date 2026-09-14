# D-114 - Seven installed VLMs on the frozen localization experiment

Identical D-113 prompts and schemas, including 0..999 box convention. This tests the installed model/backend/shared interface, not best native model performance. CPU-only isolated server; latency not a flight benchmark. Gemma is a reused historical baseline. Three scenes, one positive only.

One visible target and two absent scenes; six requests per model.
A model passes a format only if it passes the positive and both negatives. Grid and box scores measure different precision; do not sum them into a ranking.

| Model | Visible grid | Absent grid /2 | Visible box | IoU | Absent box /2 | Errors | Pending |
|---|---|---:|---|---:|---:|---:|---:|
| gemma4:e2b (saved baseline) | pass | 0 | wrong_answer | 0.0502 | 2 | 0 | 0 |
| moondream:latest | wrong_answer | 0 | invalid_output | — | 0 | 3 | 0 |
| richardyoung/smolvlm2-2.2b-instruct:Q4_K_M | runtime_error | 0 | runtime_error | — | 0 | 6 | 0 |
| qwen3-vl:2b | pass | 1 | pass | 0.5946 | 2 | 0 | 0 |
| qwen3-vl:4b | pass | 2 | pass | 0.7765 | 2 | 0 | 0 |
| qwen3-vl:8b | pass | 2 | pass | 0.7145 | 2 | 0 | 0 |
| qwen3.5:2b | pass | 1 | wrong_answer | 0.0000 | 2 | 0 | 0 |
| qwen3.5:4b | pass | 2 | wrong_answer | 0.0354 | 2 | 0 | 0 |

## Verification

{
  "requests_verified": 42,
  "maximum_new_attempts": 42,
  "historical_baseline_calls": 6,
  "cpu_residency_checks": 36,
  "cloud_calls": 0,
  "flights": 0,
  "no_runtime_changes": true,
  "pending": 0
}

All raw requests include original PNG base64, full model ID/digest, options and schema. Raw replies retain both content and thinking channels. Failed requests are retained. CPU residency records include actual context length: some backends clamp the requested 8192 tokens to their supported context. The request token budget is 192, so truncated responses and interface limitations must not be interpreted as visual incapacity.

Historical Gemma used GPU/shared-server execution. No speed ranking is justified. No weights downloaded and no flight/runtime configuration promoted.

## Finding and next step

Qwen3-VL 4B and 8B pass all three grid cases and all three box cases. Qwen3-VL 2B passes all box cases but falsely selects B2 in hidden-openings grid. Positive-box IoUs are 0.5946 (2B), 0.7765 (4B), and 0.7145 (8B), versus saved Gemma 0.0502. Qwen3.5 2B/4B boxes miss the target (IoU 0.0000/0.0354), despite correct visible grid cells.

Installed Moondream: all grid answers wrong, all three box outputs invalid. Installed SmolVLM2 package: six HTTP 400 multimodal-not-supported errors. These are shared-interface/package limitations, not proof those model families cannot perform native visual localization.

Recommendation: Qwen3-VL 4B for independent saved-frame validation before flight promotion; Qwen3-VL 2B with boxes is a smaller candidate. The 8B model offers no additional passed cases here. Use new target positions, scales and occlusions plus absent/distractor images with criteria frozen in advance. This establishes a model/backend-dependent grounding difference on these inputs, not reliable planning or navigation. No further calls or flights scheduled.
