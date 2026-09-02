# C5 prompt-only viewpoint experiment — 2026-09-02

## Hypothesis

Keep OnFly's strict image-point output `{"u": integer, "v": integer}`, but tell
the VLM that when the semantic target is absent it should choose a reachable
viewpoint maximizing new visual coverage.

No map, frontier generator, scripted scan, detector, simulator truth, model
change, or controller/planner change was introduced.

## Results

| Seed | Result | Final distance | Target-visible decision frames | Interpretation |
|---:|---|---:|---:|---|
| 1061 | success | 1.496 m | not required for gate | Positive control preserved |
| 1060 | timeout | 57.186 m | 0/89 | Worse than retained 43.206 m; target still never observed |
| 1062 | timeout | 38.771 m | 0/89 | Closer than retained 51.775 m, but target still never observed |
| 1063 | invalid/incomplete | — | — | Interrupted after a backend stall at 88.15/90 simulated seconds; not counted |

The prompt changes trajectory choice but does not create systematic coverage.
Two independent hidden-target seeds remain at zero target-visible frames, so
the prompt-only hypothesis is rejected without spending seed 1064.

The experimental wording was reverted from the frozen C5 implementation.
Future work should expose an explicit exploration state: at minimum visited-view
memory, and preferably safe frontier candidates from onboard depth/odometry.
The VLM may still return only `u,v`; the missing mechanism is stateful coverage,
not the output representation.

Runs:

- `runs/c5_shared_qwen_s1061_viewpoint_prompt_v1`
- `runs/c5_shared_qwen_s1060_viewpoint_prompt_v1`
- `runs/c5_shared_qwen_s1062_viewpoint_prompt_v1`
- incomplete: `runs/c5_shared_qwen_s1063_viewpoint_prompt_v1`

Exact replay:

- `reports/paper_implementation/c5_s1060_viewpoint_prompt_v1_analysis.json`
- `reports/paper_implementation/c5_s1062_viewpoint_prompt_v1_analysis.json`
