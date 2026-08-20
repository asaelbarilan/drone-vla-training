# Baseline: seven family bases, grid_nav, seeds 101-140

| base | family | success | collisions | failure modes |
|---|---|---|---|---|
| c0 | classical_baseline | **0.88** | 0.07 | collision 3, timeout 2 |
| c1 | llm_tool_planner | **0.70** | 0.00 | timeout 12 |
| c2 | vlm_semantic_waypointer | **0.95** | 0.05 | collision 2 |
| c3 | hybrid_stack | **0.97** | 0.03 | collision 1 |
| c6 | selective_recovery | **0.95** | 0.03 | collision 1, timeout 1 |
| c8 | direct_vla | **0.93** | 0.00 | timeout 3 |
| c12 | fast_slow_hierarchy | **0.62** | 0.00 | timeout 15 |
