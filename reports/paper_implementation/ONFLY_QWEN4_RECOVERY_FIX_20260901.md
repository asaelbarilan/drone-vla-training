# C5 OnFly/Qwen recovery correction — 2026-09-01

## What was actually broken

1. At four monitor images Ollama returned `exceed_context_size_error`: the
   request required 4430 tokens but the implicit context was 4096. The adapter
   discarded the server error and exposed an empty model response.
2. Separate history/latest images caused Qwen to attribute a historical red
   tower to the latest frame.
3. Every `LOST` monitor tick restarted the same bounded reorientation, turning
   one recovery event into a stop-turn loop.
4. A missing previous-goal reprojection overruled direct current-frame evidence
   that the target was still visible.

## Corrections

- Freeze the shared `qwen3-vl:4b` runtime at `num_ctx: 8192` and fail loudly on
  Ollama request errors.
- Serialize monitor memory as chronological history plus a large labelled
  latest panel.
- Admit one reorientation per continuous loss episode; reacquisition clears the
  latch.
- Treat a visible latest target as a fresh anchor even when the prior waypoint
  has left the image.

No detector, color threshold, simulator truth, return-to-truth motion, or
scripted target search enters the architecture. Green target boxes in visual
debug sheets are offline scoring overlays only.

## Exact gates and outcomes

- Four-image failure replay: valid `LOST` after context correction.
- Six-image near-goal replay: valid `STOP`.
- Focused verification: 51 tests pass; changed-file Ruff passes.
- Full repository verification: 367 passed; the sole failure was a pre-existing
  unrecorded deterministic-simulator dependency in the Qwen-VLA dataset
  collector. After adding that intentional dependency to the portability
  ledger, the affected contract passes.
- Seed 1061: **success**, correct terminal stop, final distance 0.652 m,
  time-to-goal 80.9 s, one recovery, zero collisions, zero inference/parse
  errors.
- Seed 1060: **failure**, zero target-visible decision frames, final distance
  39.992 m. This is the remaining never-observed-target search boundary.

Artifacts:

- `runs/c5_shared_qwen_s1061_loss_latch_v3/`
- `runs/c5_shared_qwen_s1060_loss_latch_v1/`
- `reports/paper_implementation/c5_s1061_success_visual_timeline.png`
- `reports/paper_implementation/c5_s1060_failure_visual_timeline.png`
- `reports/paper_implementation/c5_s1061_monitor_context8192_gate.json`

## Superseding retained five-seed evaluation

The final retained implementation was rerun on development seeds 1060–1064.
Only seed 1061 succeeds (0.519 m); seeds 1060, 1062, and 1063 never observe the
target, while seed 1064 observes it in 9/89 decision frames and then loses
tracking. Aggregate success is 1/5, with zero collisions and zero
inference/parse errors. The locked 4/5 gate therefore fails.

Use `C5_RETAINED_FIVE_SEED_RESULTS_20260901.md` and its listed runs for the
final result. Earlier two-seed distances in this note are debugging milestones,
not the retained aggregate.
