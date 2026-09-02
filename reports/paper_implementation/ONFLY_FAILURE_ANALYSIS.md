# OnFly local-simulator failure analysis

Date: 2026-08-26  
Scope: `C5-OnFly-Gemma-3-4B`, development seeds 1060 and 1061  
Status: diagnosis only; no architecture behavior was changed

## Bottom line

OnFly did not fail because of a crash, malformed JSON, collision, or an
infeasible planner. It failed because the semantic image target was usually
absent and, when present, Gemma 3 4B did not point to it reliably. The local
stack then converted those syntactically valid but semantically wrong pixels
into safe trajectories. Three testbed gaps amplify this upstream failure:

1. the scheduler waits for inference and then waits a full configured period,
   so the declared rates are not the achieved rates;
2. the `reject_stale` setting rejects an already-stale proposal at admission but
   does not stop an accepted trajectory after it becomes stale;
3. the component named semantic/geometric verifier currently performs geometry
   only because the paper's ViT ROI refinement is unavailable.

The failed profile is not the model profile in the paper. The paper uses
Qwen3-VL-4B-AWQ; the rejected local profile uses Gemma 3 4B. The official OnFly
repository still contains no released implementation, checkpoint, or exact
prompt, so this remains a clean-room mechanism port rather than a source
reproduction.

## What happened in the two failed flights

| Evidence | Seed 1060 | Seed 1061 |
|---|---:|---:|
| Result | timeout | timeout |
| Final goal distance | 25.7105 m | 18.1727 m |
| Path length | 38.095 m | 43.126 m |
| Collisions | 0 | 0 |
| OnFly decision calls | 33 | 33 |
| Monitor calls | 21 | 21 |
| Parse/inference errors | 0 | 0 |
| Verifier accepted / rejected | 24 / 9 | 25 / 8 |
| Monitor result | 21 CONTINUE | 21 CONTINUE |
| Exact decision frames containing the red target | 0 / 33 | 6 / 33 |
| Exact replay final-distance error | 0.0 m | 0.0 m |

The six visible seed-1061 frames were reconstructed from the logged commands;
the replay reproduced the original final score exactly. On those frames the
logged Gemma decisions had a median center error of **42.83 px** and a mean of
**59.04 px** in a 224x224 image. Its errors were 25.30, 35.56, 35.85, 49.82,
87.94, and 119.77 px. Across the complete episodes, Gemma emitted `(100,100)`
14/33 times in seed 1060 and 19/33 times in seed 1061. This is a real grounding
failure, not a distance-estimation failure: depth is sampled only after the VLM
chooses an image point.

## Ranked causal analysis

### 1. Actual root cause: the active Gemma profile does not reliably ground the target

The decision schema forces a valid `(u,v)` for every image. It has no
`target_visible`, confidence, or abstain/search state. When the target is absent,
the VLM must still invent an executable pixel. In seed 1060 the target was absent
from all 33 decision frames. In seed 1061 it was absent from 27/33 frames, and
Gemma missed it badly on the six visible frames.

The current environment offers almost no useful semantic route context before
the red tower appears: gray obstacles, sky/ground, and green distractors. A
pure image-point agent therefore needs an explicit search/reorientation contract
when the named target is absent. The current OnFly decision prompt does not
state one.

### 2. Confirmed model-adapter defect: Qwen coordinates are being interpreted in the wrong units

An offline probe used the exact seed-1061 replay frames and the current OnFly
raw-pixel prompt with Qwen3-VL 8B. Although the prompt says the image is 224x224,
the model returned values that behave like normalized 0--100 coordinates:

| Source frame | True center (px) | Returned `(u,v)` | Error if raw pixels | Error if normalized |
|---:|---:|---:|---:|---:|
| 540 | (68.0, 84.5) | (29, 37) | 61.46 px | 3.88 px |
| 648 | (120.0, 84.5) | (53, 37) | 82.13 px | 2.69 px |
| 1080 | (23.0, 81.0) | (91, 35) | 82.10 px | 179.95 px |
| 1134 | (218.0, 79.5) | (97, 32) | 129.99 px | 8.31 px |
| 1296 | (131.0, 82.0) | (58, 36) | 86.28 px | 2.39 px |
| 1728 | (200.0, 77.5) | (89, 34) | 119.22 px | 2.27 px |

Five of six frames are accurate after normalized-coordinate interpretation; one
edge-case frame is a catastrophic horizontal error. The result is sufficient
to reject the current raw-pixel adapter for this Qwen build, but not sufficient
to declare the model flight-ready. A model-specific coordinate gate is required.

This defect did **not** cause the two logged failures, because those flights used
Gemma. It explains why simply replacing Gemma with Qwen under the current
interface would still fail.

The reproducible probe is
`scripts/diagnose_onfly_coordinate_contract.py`. Ground-truth red pixels are
used only for offline scoring and never enter the policy or flight runtime.

### 3. Confirmed scheduler defect: configured frequency is added after compute time

The configuration declares a 2.0 Hz decision loop and a 0.5 Hz monitor. The
fixed charged inference time is 2.2 s for each. Each role currently performs
inference and then sleeps a full period, producing:

| Role | Declared period | Inference charge | Observed start-to-start period | Achieved rate |
|---|---:|---:|---:|---:|
| Decision | 0.5 s | 2.2 s | 2.7 s | 0.370 Hz |
| Monitor | 2.0 s | 2.2 s | 4.2 s | 0.238 Hz |

This is not a real periodic deadline scheduler. It makes a slow model slower
than its measured inference latency already requires and breaks the intended
fast-decision/slow-monitor relationship.

### 4. Confirmed staleness defect: old trajectories keep generating fresh commands

`reject_stale: true` is enforced only when a decision envelope is admitted. Once
a trajectory is accepted, each control tick generates a new command from that
old trajectory and gives the command a new one-second TTL. The old semantic
source therefore never expires at execution time.

| Decision age during control | Seed 1060 | Seed 1061 |
|---|---:|---:|
| Median | 4.05 s | 4.00 s |
| 95th percentile | 9.75 s | 8.60 s |
| Maximum | 13.00 s | 13.00 s |
| Control ticks older than the declared 8 s limit | 192 | 100 |

This is an amplifier rather than the initial cause: a wrong point remains in
authority long after it should have been held or replanned.

### 5. Confirmed fidelity gap: the verifier is geometric, not semantic/geometric

The paper refines the proposed ROI with cached ViT features before depth and
clearance checks. The local source explicitly says that feature refinement is
unavailable. Consequently, the verifier accepts a wrong semantic point whenever
its depth, geofence, and obstacle clearance are valid. It accepted 49 of the 66
wrong/uncertain proposals across these runs.

Accepted verifier events are logged as `reason: "ok"`, so the trace also hides
the missing semantic stage even though the source documentation acknowledges it.

### 6. Missing recovery behavior: `LOST` has no executable consequence

The C5 profile has `recovery: null`. The monitor can output `LOST`, but the
orchestrator acts only on `STOP`; it does not stop/reorient/recover on `LOST`.
Both failed runs produced only CONTINUE, so this was not directly triggered,
but seed 1060 demonstrates the regime where the missing behavior matters: the
goal never enters a decision frame.

## What is not the root cause

- **Depth camera:** depth was present, synchronized, and used after pixel
  selection. The semantic pixel was wrong first.
- **Planner/controller collision avoidance:** the planner produced feasible
  trajectories and both flights had zero collisions. It safely executed the
  wrong intent.
- **Monitor termination:** neither flight got close enough for STOP to be the
  active issue. The all-CONTINUE result is not yet evidence that STOP is broken.
- **Two-metre success radius:** the paper uses 5 m, but the failures ended 18.2 m
  and 25.7 m away, so changing the radius cannot rescue them.
- **224-pixel image alone:** the target is small and edge cases are harder, but
  Qwen localized five of six visible frames after the coordinate convention was
  interpreted correctly.

## Smallest valid next sequence

Do not run more development seeds yet. The next work should remain one change at
a time:

1. Correct the shared scheduler's start-to-start deadline semantics and enforce
   source staleness at command execution. These are testbed correctness fixes,
   not OnFly tuning.
2. Lock a model-specific coordinate adapter with an offline visible-frame gate.
   For the installed Qwen3-VL 8B build, explicitly request/scale normalized
   0--100 coordinates and retain the unscaled output in provenance. Require a
   robust median and an edge-case bound before flight.
3. Run **only seed 1061** as `C5-OnFly-Qwen3-VL-8B-adapted-seed1061`. This seed
   separates visible-target grounding from search because it contains six
   target-visible decision frames.
4. Only after seed 1061 works, address absent-target search/LOST recovery and
   rerun **only seed 1060**.
5. Once the full C5 mechanism works, test the C3-OnFly and C4-OnFly ablations
   against the same profile and seeds. Do not tune all three simultaneously.

## Primary sources

- OnFly paper: https://arxiv.org/abs/2603.10682
- Official repository: https://github.com/Robotics-STAR-Lab/OnFly

