# OnFly implementation lock

Status: mechanism lock and compatible-backend rejection, 2026-08-27. The paper is public; the authors' official
repository still says **code coming soon**. This is therefore a clean-room,
normalized testbed implementation, not a checkpoint/source reproduction.

## Frozen paper mechanism

- Input: synchronized first-person RGB-D, odometry, and the current language
  subtask.
- Decision agent: current image plus the previous 3D goal reprojected as a 2D
  history point; strict integer image target `(u,v)`; no metric coordinates or
  motor action authored by the VLM.
- Geometry: depth is capped at `D_max=7 m`; large horizontal bearing shortens
  forward range with the paper's Gaussian bearing gate; the result is lifted
  through declared camera intrinsics.
- Verification: waypoint provenance, depth, clearance, altitude, geofence, and
  endpoint feasibility are checked before the planner.
- Execution: the common receding-horizon planner and controller remain below
  semantic waypoint authority.
- Monitoring: independent asynchronous forced choice over `CONTINUE`, `STOP`,
  and `LOST`, once every 2 s; two consecutive STOP outputs are required.
- Hybrid memory: first frame + four distance-segment keyframes + latest frame;
  candidates are triggered by translation/rotation and visually deduplicated.
- Active model profile: local Qwen3-VL 4B through the shared real Ollama
  backend, with its 0--999 relative-coordinate convention explicitly adapted
  to calibrated pixels. This matches the paper's parameter scale, but uses an
  Ollama Q4_K_M build rather than the paper's AWQ runtime. Qwen3-VL 8B and the
  earlier Gemma profiles remain rejected capability records.
- LOST execution: stop translation, then restore the yaw stored at the last
  monitor-confirmed normal visual frame. The turn is bounded to 2 s; once the
  heading is reached, hold that viewpoint until a later monitor verdict
  confirms reacquisition. It must not face or return to the old point's
  position, which the paper does not command.

## C3/C4/C5 mapping

| Profile | Paper mechanism present | Experimental role |
|---|---|---|
| `c3_onfly_qwen` | decision, verifier, planner | no monitoring control |
| `c4_onfly_qwen` | C3 + independent monitor + recent window | dual-agent effect |
| `c5_onfly_qwen` | C4, changing only memory to hybrid | memory effect |

These are profiles of the existing canonical C3/C4/C5 designs. They are not
additional benchmark families and do not create a private OnFly runtime.

## Explicit normalized choices

- The paper uses Qwen3-VL-4B-AWQ; the normalized profile uses local
  `qwen3-vl:4b` Q4_K_M (`1343d82ebee3`). The exact third-party AWQ files were
  also loaded through Transformers, but one bounded monitor response took
  178.09 s and peaked at 10.56 GiB, so that runtime cannot satisfy OnFly's 2 s
  monitor cycle. Neither result is claimed checkpoint-equivalent to unreleased
  author code.
- The unreleased implementation does not expose the shared ViT features,
  separate decoder KV caches, task-decomposition prompt, semantic feature ROI,
  or exact Fast-Planner integration. The testbed uses RGB visual deduplication,
  independent requests, the common typed verifier, and the frozen shared local
  planner. None is reported as native OnFly code.
- The 2D local simulator holds altitude after lifting a target. Vertical and
  multi-stage OnFly evaluation remains a later simulator stage.
- `sigma_theta=0.65`, 2 m translation / 20 degree rotation candidate triggers,
  visual deduplication epsilon `0.08` within 3 m geometric neighbors, and two
  STOP confirmations are locked testbed choices because the paper does not
  publish those values.

## Acceptance gate

- Config grammar passes for C3/C4/C5 profiles.
- Same-seed decisions are typed and repeatable at temperature zero.
- C4 and C5 differ only in their memory plugin/declared memory mode.
- At least 4/5 development seeds succeed in the local RGB-D grid with zero
  collision and no privileged, detector, or scripted-policy fallback.
- The monitor fires, receives actual retained sensor images, and influences
  termination; a component merely firing is insufficient.
- Held-out seeds 1-40 remain untouched until the development gate passes.

Failure of the real-model gate is a capability result. It must not be repaired
with target coordinates, sensor-side semantic detections, scripted pixels, or a
policy-specific obstacle-avoidance routine.

## Gate outcome — reopened after executable root-cause correction

The earlier rejection concealed three executable defects. Ollama rejected the
fourth monitor image because the request needed 4430 tokens while the implicit
context was 4096; the adapter silently treated the server error as an empty
answer. Independent images also made Qwen confuse historical target views with
the latest view, and every repeated LOST verdict restarted the same recovery.

The runtime now freezes `num_ctx: 8192` for the shared checkpoint and raises on
Ollama server errors. The monitor uses a chronological sheet with a dominant,
explicitly labelled latest frame. LOST starts one bounded reorientation per
continuous loss episode; current visual reacquisition resets the episode, and
a stale previous-goal reprojection cannot overrule a visibly present target.

With those corrections, predetermined seed 1061 succeeds: terminal distance
0.652 m, correct monitor stop, one recovery trigger, zero collisions, zero
policy/monitor parse errors, and 0.95 offline latest-visibility accuracy. Exact
visual replay confirms target grounding, occlusion, reacquisition, approach and
stop. Seed 1060 still fails with 0/89 target-visible decision frames: after
clearing clutter it has no observation that identifies which hidden direction
contains the red tower. This is a semantic-search limitation, and it must not
be hidden by simulator truth or scripted target-specific steering.

The retained implementation was then evaluated on all five development seeds.
Seed 1061 succeeds at 0.519 m. Seeds 1060, 1062, and 1063 have zero
target-visible decision frames; seed 1064 sees the target in its first 9 frames
and then loses it. Aggregate success is 1/5, with zero collisions and zero
inference/parse errors.

Status: mechanism demonstrated; compatible backend executes reliably but the
locked 4/5 capability gate is **rejected**. Evidence:
`reports/paper_implementation/C5_RETAINED_FIVE_SEED_RESULTS_20260901.md`.
