# Model latency profiles

These files set **simulated compute cost**, not model capability. They exist so
that timing is a stated experimental parameter rather than a property of the
machine that happened to run the sweep.

The numbers are *budgets chosen to bracket the ranges reported in the
literature* for each family — a fast learned executor around 10 Hz, a semantic
decision loop in the hundreds of milliseconds, a slow monitor or reasoner in the
seconds. They are **not** measurements, and no result produced with them is a
claim about any published system.

Two rules keep them honest:

1. **Within a matched comparison, the profile is frozen.** C7 and C8 must use
   the same profile, or the safety-shield contrast would also be a latency
   contrast.
2. **When a real model is integrated, its profile is measured, not assumed.**
   The `simulated` backend is replaced by a real `InferenceBackend`; nothing
   else in the architecture changes.

| Profile | Intended shape |
|---|---|
| `sim_free.yaml` | Zero-cost. Oracle control ceiling and unit tests only. |
| `sim_llm_skill.yaml` | Slow, infrequent, coarse authority: an LLM emitting skills. |
| `sim_vlm_waypoint.yaml` | A VLM grounding a waypoint every few hundred ms. |
| `sim_dual_loop.yaml` | Fast decision loop plus a much slower monitor. |
| `sim_vla_fast.yaml` | A learned action policy at roughly 10 Hz. |
| `sim_slow_reasoner.yaml` | An expensive reasoner, seconds per call. |
