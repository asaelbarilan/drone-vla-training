# D-104 capability screen

Read [FINDINGS.md](FINDINGS.md) before interpreting the binary scores.

- Development screen: one seed (1061), one run per cell, maximum 60 simulated seconds; no tuning or statistical ranking.
- C0 has privileged final-goal coordinates. Its current policy does not implement ordered objectives or distance-band tracking.
- C1 retains its text-only sensor/skill protocol; these scenes supply no semantic detections. It cannot visually identify task objects. Gemma replaces the historical GPT-OSS backend.
- C5 uses the existing generic current-frame OnFly monitor, calibrated camera pitch -0.10 rad, no target-color guard; this differs from the earlier guarded red-tower profile.
- Latency is not matched: C1 retains 8.5 s simulated policy charge; C5 retains 1 s policy / 1.2 s monitor. Actual wall times and model requests are saved.
- C0 inference entries are zero-token simulator events. C1 and C5 use local gemma4:e2b only. No cloud calls or held-out seeds.

| Scenario | C0 | C1 | C5 |
|---|---|---|---|
| known_goal | [PASS](http://127.0.0.1:8765/capability_screen_c0.html#run=capability_screen_c0_known_goal_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c1.html#run=capability_screen_c1_known_goal_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c5.html#run=capability_screen_c5_known_goal_20260912_s1061&t=0) |
| visible_target | [PASS](http://127.0.0.1:8765/capability_screen_c0.html#run=capability_screen_c0_visible_target_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c1.html#run=capability_screen_c1_visible_target_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c5.html#run=capability_screen_c5_visible_target_20260912_s1061&t=0) |
| turn_search | [PASS](http://127.0.0.1:8765/capability_screen_c0.html#run=capability_screen_c0_turn_search_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c1.html#run=capability_screen_c1_turn_search_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c5.html#run=capability_screen_c5_turn_search_20260912_s1061&t=0) |
| overturned_vehicle | [PASS](http://127.0.0.1:8765/capability_screen_c0.html#run=capability_screen_c0_overturned_vehicle_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c1.html#run=capability_screen_c1_overturned_vehicle_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c5.html#run=capability_screen_c5_overturned_vehicle_20260912_s1061&t=0) |
| conditional_gate | [PASS](http://127.0.0.1:8765/capability_screen_c0.html#run=capability_screen_c0_conditional_gate_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c1.html#run=capability_screen_c1_conditional_gate_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c5.html#run=capability_screen_c5_conditional_gate_20260912_s1061&t=0) |
| ordered_visit | [FAIL: agent_stopped](http://127.0.0.1:8765/capability_screen_c0.html#run=capability_screen_c0_ordered_visit_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c1.html#run=capability_screen_c1_ordered_visit_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c5.html#run=capability_screen_c5_ordered_visit_20260912_s1061&t=0) |
| closing_passage | [PASS](http://127.0.0.1:8765/capability_screen_c0.html#run=capability_screen_c0_closing_passage_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c1.html#run=capability_screen_c1_closing_passage_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c5.html#run=capability_screen_c5_closing_passage_20260912_s1061&t=0) |
| follow_target | [FAIL: agent_stopped](http://127.0.0.1:8765/capability_screen_c0.html#run=capability_screen_c0_follow_target_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c1.html#run=capability_screen_c1_follow_target_20260912_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/capability_screen_c5.html#run=capability_screen_c5_follow_target_20260912_s1061&t=0) |

## Evidence

Per-cell manifest.json and result.json are copied here; C0/C1/C5_SUMMARY.json contain metrics and replay hashes. Original events and exact model requests/responses remain under runs/<run>/ with debug capture. Browser checks/screenshots are under browser/. No failed flight is removed or rerun.
