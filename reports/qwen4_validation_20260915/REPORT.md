# D-115: Qwen3-VL4B new-frame validation

PASS — ready for the conditional flight

All 6 pass. Each positive: IoU>=0.5 and center inside reference. Each negative: visible=false and zero box. No retries or prompt changes.

Six new image hashes relative to D-113/D-114, not six independent worlds. Two positive frames share one hover flight, and one positive comes from the earlier clutter seed. This is a small diagnostic gate, not a planning or generalization benchmark.

| Case | Expected | Result | IoU | Center on target |
|---|---|---|---:|---|
| far_left | visible | pass | 0.7704 | True |
| mid_center | visible | pass | 0.9383 | True |
| close_clipped | visible | pass | 0.9767 | True |
| absent_clutter_1060 | absent | pass | — | — |
| absent_clutter_1062 | absent | pass | — | — |
| absent_after_turn | absent | pass | — | — |

Six new input hashes relative to D-113/D-114. Source bytes and observation IDs checked. Reference boxes visually inspected before inference; none sent to model. CPU-only execution, no cloud calls or retries. Full model digest/options/requests/replies preserved.

Verified 6 request identities. Conditional flight permitted: True.

## Subsequent flight completed

See [FLIGHT_REPORT.md](FLIGHT_REPORT.md): one Qwen clutter flight timed out;
closest 13.75 m versus Gemma 22.58 m. Recovery diagnosis includes actual and
counterfactual views. Image-gate success does not imply navigation success.
