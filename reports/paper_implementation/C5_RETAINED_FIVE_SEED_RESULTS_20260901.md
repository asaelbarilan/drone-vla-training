# C5 OnFly retained five-seed result — 2026-09-01

## Frozen evaluation

- Architecture: `c5_onfly_qwen4_native_dynamics`
- Shared model for both policy and monitor: `qwen3-vl:4b`
- Expected Ollama digest:
  `9c60bdd691c1897bbfe5ddbc67336848e18c346b7ee2ab8541b135f208e5bb38`
- Environment: `grid_nav_onfly_native_dynamics`
- Development seeds: 1060–1064
- No privileged observations, detector, scripted target search, or
  simulator-truth steering

## Results

| Seed | Result | Final distance | Closest | Path | Visible decision frames | Monitor LOST | Recovery triggers | Diagnosis |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1060 | timeout | 43.206 m | 24.582 m | 46.318 m | 0/89 | 33 | 2 | Target never observed; false acquisition/loss cycle |
| 1061 | **success** | **0.519 m** | 1.277 m | 45.128 m | 38/85 | 7 | 2 | Correct acquisition, recovery, approach, and visual stop |
| 1062 | timeout | 51.775 m | 24.526 m | 48.107 m | 0/89 | 0 | 0 | Target never observed; policy continued in the wrong direction |
| 1063 | timeout | 26.813 m | 19.527 m | 45.083 m | 0/89 | 32 | 5 | Target never observed; repeated false acquisition/loss cycle |
| 1064 | timeout | 53.533 m | 25.829 m | 45.220 m | 9/89 | 40 | 1 | Target visible from 0–7.95 s, then tracking lost |

Aggregate: **1/5 success (20%)**, zero collisions, zero inference errors, and
zero policy/monitor parse errors.

## What was fixed

1. Ollama monitor requests now use `num_ctx: 8192` and server errors are
   surfaced instead of becoming empty answers.
2. Monitor memory is rendered as a chronological history sheet plus a separate
   large latest frame.
3. Acquisition requires two consecutive latest-frame positive observations;
   history alone cannot acquire the target.
4. One bounded recovery is admitted per continuous LOST episode.
5. Rejected waypoint feedback is returned to the visual policy.

Seed 1061 still succeeds after these corrections. Seed 1062's former
history/latest false acquisition is also removed. The remaining failures are
therefore retained capability failures rather than runtime or parser failures.

## Rejected fixes

- An explicit `target_visible`/ground-point policy schema regressed the real
  seed-1061 success and was reverted.
- A one-sided scripted pre-acquisition scan missed the target and caused later
  hallucinated acquisition; it was removed.
- Requiring cross-agent agreement suppressed some false positives but depended
  on the regressive policy schema and was removed.

## Decision

C5 demonstrates the intended OnFly mechanism but **fails the locked 4/5
development gate**. Freeze this result for the paper rather than adding hidden
target-specific search. The next architecture should proceed independently;
future C5 work should be framed as learned/general semantic search or a stronger
shared VLM, then rerun the same five development seeds.

Retained run directories:

- `runs/c5_shared_qwen_s1060_retained_final_v2`
- `runs/c5_shared_qwen_s1061_retained_final_v5`
- `runs/c5_shared_qwen_s1062_history_latest_v3`
- `runs/c5_shared_qwen_s1063_retained_final_v3`
- `runs/c5_shared_qwen_s1064_retained_final_v2`

Exact offline replay reports:
`reports/paper_implementation/c5_s1060_retained_analysis.json` through
`c5_s1064_retained_analysis.json`.
