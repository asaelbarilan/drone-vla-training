| base | family | success | 95% CI | collisions | median distance WHEN IT FAILS | failure modes |
|---|---|---|---|---|---|---|
| c0 | classical_baseline | **0.80** | 0.60 - 0.95 | 0.15 | 21.5 m | collision 3, timeout 1 |
| c1 | llm_tool_planner | **0.45** | 0.25 - 0.65 | 0.00 | 30.2 m | timeout 11 |
| c2 | vlm_semantic_waypointer | **0.70** | 0.50 - 0.90 | 0.05 | 32.1 m | timeout 5, collision 1 |
| c3 | hybrid_stack | **0.60** | 0.40 - 0.80 | 0.05 | 29.7 m | timeout 7, collision 1 |
| c6 | selective_recovery | **0.60** | 0.40 - 0.80 | 0.05 | 29.7 m | timeout 7, collision 1 |
| c8 | direct_vla | **0.55** | 0.35 - 0.75 | 0.00 | 29.3 m | timeout 9 |
| c12 | fast_slow_hierarchy | **0.55** | 0.35 - 0.75 | 0.00 | 29.8 m | timeout 9 |
