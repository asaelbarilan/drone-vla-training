# D-106 frozen capability comparison

Authorized scope: validate corrected AerialClaw search once, inspect dashboard,
then compare three frozen architecture families across the eight existing tasks.
Exactly 24 fresh development flights, seed 1061, at most 60 sim seconds each;
the first search validation IS its matrix cell, never repeated. No adaptive fixes,
latency changes, cloud calls or model swaps. Stop on runtime error; retain evidence.

Profiles fixed BEFORE the first flight:
- C0: c0, all eight capability environments; privileged final-goal baseline.
- C5: c5_capability_gemma_dev, all eight; generic current-frame OnFly monitor.
- C1 known_goal: c1_capability_gemma_dev, repaired public-coordinate completion.
- C1 visible_target / turn_search: c1_visual_search_gemma_dev with corresponding
  capability_*_tools environment. Only allowed skill vocabulary differs from the
  base scene; identical geometry, sensor, task scoring, seed and horizon.
- C1 other five cells: existing c1_capability_gemma_dev TEXT-ONLY profile. These
  are explicitly integration-limited compatibility checks, not evidence that a
  visually equipped AerialClaw architecture cannot reason about the task.

C1 charges 8.5 sim seconds per policy request, requested perception 1.2;
C5 policy 1 / monitor 1.2. This is NOT matched latency or a paper ranking.
One seed cannot establish reliability. No new verifier/planner is introduced.

Freeze contains resolved configs and source hashes. Runner verifies these before
all flights. Each cell saves exact requests/images, events, manifest and result.
Dashboard inspection pairs camera and motion with source-aligned decisions.
Failures are classified as demonstrated contract bug, known missing capability,
observed policy behavior, or unresolved cause. Symptoms are not root causes.
