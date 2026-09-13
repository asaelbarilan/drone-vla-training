# D-106 frozen capability comparison

See FINDINGS.md and SEARCH_INSPECTED.md for diagnosis.

- 24 fixed cells, development seed 1061, maximum 60 simulated seconds; no adaptive changes or retries.
- C0 is a privileged final-goal baseline, not an autonomous visual searcher.
- C1 uses the requested visual tool only for visible target/search. Five other visual-task cells remain text-only and integration-limited.
- C1 policy costs 8.5 simulated seconds; C5 policy 1 second. Perception/monitor cost 1.2 seconds. This is not a matched-latency ranking.
- Search diagnosis: target appears during rotation but was absent in the sole post-scan detection image; inherited full-turn gate rejects another scan.
- Click each result for the actual camera, flight, decisions and exact model input. Timeout alone is not a root-cause diagnosis.

| Scenario | C0 | C1 | C5 |
|---|---|---|---|
| known_goal | [PASS](http://127.0.0.1:8765/frozen_capability_c0.html#run=frozen_c0_known_goal_20260913_s1061&t=0) | [PASS](http://127.0.0.1:8765/frozen_capability_c1.html#run=frozen_c1_known_goal_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c5.html#run=frozen_c5_known_goal_20260913_s1061&t=0) |
| visible_target | [PASS](http://127.0.0.1:8765/frozen_capability_c0.html#run=frozen_c0_visible_target_20260913_s1061&t=0) | [PASS](http://127.0.0.1:8765/frozen_capability_c1.html#run=frozen_c1_visible_target_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c5.html#run=frozen_c5_visible_target_20260913_s1061&t=0) |
| turn_search | [PASS](http://127.0.0.1:8765/frozen_capability_c0.html#run=frozen_c0_turn_search_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c1.html#run=frozen_c1_turn_search_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c5.html#run=frozen_c5_turn_search_20260913_s1061&t=0) |
| overturned_vehicle | [PASS](http://127.0.0.1:8765/frozen_capability_c0.html#run=frozen_c0_overturned_vehicle_20260913_s1061&t=0) | [FAIL: timeout — missing visual integration](http://127.0.0.1:8765/frozen_capability_c1.html#run=frozen_c1_overturned_vehicle_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c5.html#run=frozen_c5_overturned_vehicle_20260913_s1061&t=0) |
| conditional_gate | [PASS](http://127.0.0.1:8765/frozen_capability_c0.html#run=frozen_c0_conditional_gate_20260913_s1061&t=0) | [FAIL: timeout — missing visual integration](http://127.0.0.1:8765/frozen_capability_c1.html#run=frozen_c1_conditional_gate_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c5.html#run=frozen_c5_conditional_gate_20260913_s1061&t=0) |
| ordered_visit | [FAIL: agent_stopped](http://127.0.0.1:8765/frozen_capability_c0.html#run=frozen_c0_ordered_visit_20260913_s1061&t=0) | [FAIL: timeout — missing visual integration](http://127.0.0.1:8765/frozen_capability_c1.html#run=frozen_c1_ordered_visit_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c5.html#run=frozen_c5_ordered_visit_20260913_s1061&t=0) |
| closing_passage | [PASS](http://127.0.0.1:8765/frozen_capability_c0.html#run=frozen_c0_closing_passage_20260913_s1061&t=0) | [FAIL: timeout — missing visual integration](http://127.0.0.1:8765/frozen_capability_c1.html#run=frozen_c1_closing_passage_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c5.html#run=frozen_c5_closing_passage_20260913_s1061&t=0) |
| follow_target | [FAIL: agent_stopped](http://127.0.0.1:8765/frozen_capability_c0.html#run=frozen_c0_follow_target_20260913_s1061&t=0) | [FAIL: timeout — missing visual integration](http://127.0.0.1:8765/frozen_capability_c1.html#run=frozen_c1_follow_target_20260913_s1061&t=0) | [FAIL: timeout](http://127.0.0.1:8765/frozen_capability_c5.html#run=frozen_c5_follow_target_20260913_s1061&t=0) |
