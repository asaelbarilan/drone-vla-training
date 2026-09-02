# Qwen checkpoint selection protocol for OnFly

Date: 2026-08-27

## Decision question

Which official, downloadable Qwen vision-language checkpoint is the strongest
practical OnFly backend for the local RTX 4060 Laptop GPU (8 GB), while keeping
warm latency and memory compatible with onboard-style experimentation?

## Scope and acceptance criteria

- Candidates: official Qwen3-VL 4B AWQ and newer official Qwen3.5 multimodal
  checkpoints small enough to run locally.
- Required: image input, redistributable research use, released weights,
  documented runtime, and credible fit in 8 GB VRAM.
- Runtime gate: load locally and complete the locked OnFly coordinate and
  positive/negative monitor probes without parser errors.
- Capability gate: useful pixel grounding, correct red/green discrimination,
  and correct near-goal STOP semantics.
- Exclude: text-only checkpoints, API-only models, checkpoints exceeding the
  hardware envelope, and unofficial conversions when an official equivalent
  exists.

## Search protocol

- Sources: official Qwen Hugging Face organization, Qwen GitHub/model cards,
  official Ollama registry, and the already validated UAV evidence ledger.
- Search terms: `Qwen3-VL-4B-Instruct-AWQ`, `Qwen3.5 vision 2B 4B AWQ`,
  `Qwen3.5 multimodal model card`, and `Qwen3.5 Ollama vision`.
- Date range: current releases available on 2026-08-27; foundational context is
  inherited from `spf_evidence.json`.
- Stopping rule: stop after all official sub-8B Qwen vision candidates and
  their licenses, formats, and resource requirements are resolved.

This is a narrow checkpoint-selection update, not a new architecture review.
The existing validated 31-work evidence ledger supplies the broader UAV/VLM
context; only newly material checkpoint resources are added here.
