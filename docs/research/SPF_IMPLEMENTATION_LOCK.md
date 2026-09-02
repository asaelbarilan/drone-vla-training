# See, Point, Fly implementation lock

Locked: 2026-08-25, before C2 implementation or development episodes.

## Reproduced mechanism

- Input: current RGB frame, natural-language mission and calibrated camera
  dimensions/FOV. No depth, semantic detections, map truth or goal coordinates.
- Frozen real VLM output: exactly one JSON object with integer image coordinates
  `u`, `v` and integer intended-travel label `distance` in `[1, 10]`.
- Adaptive distance: `max(0.1, 10 * (distance / 10) ** 1.8)` metres.
- Pinhole lift: normalized horizontal/vertical image coordinates multiplied by
  adaptive distance and tangent of the corresponding half-FOV.
- Frame transform: body-frame right/forward/up displacement to absolute ENU
  using observed yaw; clamp only to the common minimum flight altitude.
- Closed loop: one new RGB-grounded waypoint per policy inference.
- Termination normalization: two consecutive valid outputs with
  `distance <= 2` become an explicit `MissionDirective(STOP)`. No world distance
  or depth participates.

## Intentionally normalized surroundings

SPF's yaw/pitch/throttle queue is replaced after the 3-D displacement by C2's
typed `WaypointGoal -> common decision router -> frozen SUPER -> common
controller`. C2 deliberately has no semantic/geometric proposal verifier; that
mechanism first appears in C3. The policy may point around visible obstacles,
while geometric collision avoidance remains common execution substrate.

## Model/resource lock

Candidate: locally installed `qwen3-vl:8b`, Ollama digest prefix
`901cae732162`, official Qwen3-VL Apache-2.0 release. Greedy decoding, pinned
sampling seed, JSON response schema, no hidden textual fallback. A missing
daemon/model, empty response, invalid JSON, missing field or out-of-range value
is an explicit policy failure.

The 8B candidate may be rejected only by the fixed probe/gate. The already
installed 2B model is the predeclared smaller fallback to test if 8B is
operationally infeasible, not a quality-driven post-hoc substitute. Gemma's old
depth-assisted policy is not an SPF fallback. If both locked candidates are
falsified, additional real VLMs may be audited only as an explicitly recorded
blocker-resolution step; the schema, policy mechanism, seeds and gate remain
unchanged.

## Development seeds and tasks

Held-out seeds 1-40 remain untouched. SPF development/gating uses seeds
**1040-1044**, selected before probing and distinct from SUPER 1000-1019 and
AerialClaw 1020-1024.

- `grid_nav` with rendering enabled: target initially within sensing range;
  tests grounding, adaptive approach, obstacle-safe execution and autonomous
  stopping.
- `object_search` with rendering enabled: target initially beyond the short
  sensing horizon with decoys; tests whether the real VLM's closed loop can
  produce non-oracle search motion and then ground the target.

## Acceptance gate

SPF/C2 is accepted only if all of the following hold:

- unit/contract tests prove the published adaptive scaling and camera lift,
  strict typed schema, valid ENU waypoint, two-output stop rule and fail-closed
  inference behavior;
- policy instrumentation proves every waypoint derives from an RGB VLM output
  containing `(u,v,distance)`, and each log records the label, adaptive distance,
  normalized point, typed decision and shared SUPER plan without raw model prose;
- a guard test proves the policy cannot access `semantic_hits`, observation
  `privileged`, depth frames or environment goal state;
- real `qwen3-vl:8b` completes at least **4/5 `grid_nav`** episodes and at least
  **2/5 `object_search`** episodes on seeds 1040-1044, with zero collisions,
  zero model/script fallbacks and no invalid model outputs;
- all successful episodes terminate through the predeclared repeated-near-label
  rule rather than environment/scoring truth;
- repeating `grid_nav` seed 1040 agrees on outcome, termination, ordered typed
  decision sequence and final distance within 0.25 m; exact `(u,v,distance)`
  equality is retained and reported separately;
- the held-out-seed list in the machine-readable report is empty;
- focused tests, configuration validation, changed-file Ruff and the full local
  regression suite pass.

The object-search threshold is deliberately non-trivial because SPF claims
search competence. If the local VLM cannot meet it without a scripted pattern,
that is a model/resource blocker or a falsifying result, not permission to add
oracle search.

## Development result: mechanism complete, backend gate blocked

The implementation and contract suite pass, but no audited local VLM meets the
locked capability interface. Gemma 3 4B mispoints to `(5,5)`; Qwen3-VL 2B has
non-monotonic close-range labels; Gemma 4 emits constant label 5; Gemma 3 12B
improves point grounding but never emits a near label at 1.5-2 m. Qwen3-VL 8B
is the best local grounder and entered the goal region, but did not produce the
required repeated near-label stop and flew away. Single-label and metric-prompt
variants caused premature stops or lost-target flight and were reverted.

The machine-readable evidence is
`reports/paper_implementation/spf_backend_audit.json`. Seeds 1-40 were not used.
SPF/C2 is therefore **not accepted or frozen**. The minimum resolution is a
Gemini-class backend or compatible open checkpoint that passes this unchanged
probe and gate; depth, target-size scripts, oracle distance and relaxed success
criteria remain forbidden.
