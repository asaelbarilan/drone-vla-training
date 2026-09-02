# C5 OnFly — Qwen3-VL 8B root-cause analysis

Date: 2026-08-26  
Scope: local RGB-D simulator, development seed 1061 only  
Architecture: `c5_onfly_qwen`  
Model: local `qwen3-vl:8b`, digest
`901cae73216286ea8c5aba8b46d307ff7188f737285ec500c795a12f05225d28`

## Outcome

The system now works on the diagnostic seed. Run
`runs/onfly_c5_qwen_seed1061_v6` terminated with a correct monitor stop 1.606 m
from the red tower at 69.2 simulated seconds, with zero collisions, zero stale
commands, zero inference errors, and zero parse errors. Exact offline replay
reproduced the stored final distance with 0.0 m error.

This is one development-seed pass, not the 4/5 acceptance gate and not a
held-out benchmark result.

## What was actually broken

Four independent defects/gaps were exposed in order.

1. **The asynchronous scheduler added a full period after inference.** This
   changed the intended 2 Hz / 0.5 Hz relationship. It now uses start-to-start
   deadlines without catch-up bursts.
2. **Accepted trajectories did not expire at execution time.** Fresh control
   commands could inherit arbitrarily old semantic intent. The router now
   rejects the source once its declared decision age expires.
3. **The Qwen coordinate adapter was wrong.** The local Qwen build uses a
   0--999 relative coordinate grid. The locked six-frame offline gate has
   1.01 px mean and 2.51 px maximum calibrated replay error.
4. **LOST recovery used the wrong geometric quantity.** The paper says to
   reorient to the *heading at the last normal point*. The implementation faced
   the *position of the last normal point*, which commonly points backward
   along the travelled path. It repeatedly reacquired and then lost the target
   without converging. Recovery now restores the stored normal yaw exactly.

The fourth defect was decisive on seed 1061. No target coordinates, simulator
semantic detections, scripted pixel, oracle waypoint, or privileged state was
added to the architecture.

## Controlled run sequence

| Run | Relevant mechanism | Result | Final / closest distance |
|---|---|---:|---:|
| v2 | Qwen adapter, verifier/scheduler fixes; no executable LOST recovery | timeout | 70.25 / 14.70 m |
| v4 | fixed recovery, but independent monitor calls forgot prior acquisition | timeout | 25.45 / 14.51 m |
| v5 | persistent model-derived acquisition bit; recovery faced old position | timeout | 16.87 / 14.66 m |
| v6 | recovery restores old normal heading | **success** | **1.61 / 1.61 m** |

All comparisons use architecture `c5_onfly_qwen`, environment
`grid_nav_onfly`, and seed 1061. The exact reports are
`onfly_c5_qwen_seed1061_v{2,4,5,6}_analysis.json`.

## Why the earlier flights wandered

The decision schema always requires an executable `(u,v)`, including when the
target is occluded. In v5 the tower was visible in only 25/89 decision frames.
When visible, the calibrated point was usually useful (2.02 px median center
error), and the following interval reduced goal distance by 0.555 m on average.
When absent, distance changed by only -0.054 m per interval on average. Thus
the model was not failing primarily at distance measurement: it was losing the
semantic target, emitting a compulsory point under partial observability, and
then being recovered in the wrong direction.

The slow monitor remains imperfect. Its latest-frame visibility accuracy was
62.2% in v5 and 81.8% in v6. In v6 it produced three false LOST labels while
the tower was visible and three CONTINUE labels while it was absent. The
paper-defined bounded recovery tolerated these errors once it restored the
correct heading. This limitation must still be measured over the remaining
development seeds.

Near the goal, image-center error is not a valid grounding metric because the
policy deliberately selects a reachable base/approach point rather than the
center of the tall tower. The valid terminal evidence is synchronized depth,
two consecutive monitor STOP decisions, and the independent geometric success
check. v6 satisfied all three.

## What was not the cause

- The depth camera was synchronized and used only after the model selected a
  pixel. The 7 m cap delayed neither arrival nor the final stop.
- SUPER produced executable plans throughout v6; no plan was infeasible.
- The controller maintained 20 Hz and there were no stale actions.
- The Qwen JSON contract had no parse or inference failures.
- The 2 m benchmark radius did not rescue a distant timeout: v6 physically
  reached 1.606 m and stopped.

## Remaining fidelity limits

The authors' repository still does not release the implementation. The testbed
therefore cannot reproduce the paper's exact prompt, shared ViT feature tensor,
semantic ROI refinement, independent persistent KV caches, or TensorRT/AWQ
runtime. The local profile uses Qwen3-VL 8B through Ollama and the frozen SUPER
substrate. These are declared normalized choices, not native OnFly code.

Primary sources:

- https://arxiv.org/abs/2603.10682
- https://github.com/Robotics-STAR-Lab/OnFly

## Next gate

Run the remaining development seeds sequentially. Freeze C5 OnFly only if at
least 4/5 pass with zero collisions and correct terminal stops. Do not run C3,
C4, PMR, AirSim, or Gazebo before this gate is resolved.

### Seed-1060 update

Seed 1060 remains a clean failure after the recovery correction. Exact replay
of both Qwen flights found **0 target-visible decision frames out of 89**. In
v1, Qwen confused a green tower-like distractor with the requested red tower at
27.2 s, armed acquisition, and then invoked 30 false LOST recoveries. A generic
prompt requirement that all named attributes match corrected that exact frame.
In v2, however, Qwen again claimed that the red target existed in history at
11.2 s even though all four monitor images contained only the green distractor;
the result is reproducible offline. The run then invoked 27 recoveries and
timed out 33.54 m from goal.

This is a capability failure in semantic attribute discrimination and unseen-
target exploration, not a depth, planner, controller, or timing failure. The
paper-defined strict `(u,v)` decision output has no explicit pre-acquisition
abstain/search state. No scripted scan or color detector will be added to make
the profile pass. Qwen3-VL 2B and Qwen3.5 2B were also rejected by the same
negative/positive offline monitor gate; Qwen3-VL 8B remains the best installed
profile and retains the correct positive STOP on seed-1061 near-goal frames.

The scientifically controlled final-profile rerun is seed-1060 v3, after both
`d_f` geometry corrections. It failed by **premature STOP at 28.41 m after
15.2 s**. Exact replay found 0/15 target-visible decision frames and reproduced
the final distance with 0.0 m error. Qwen first produced one false STOP that
the two-confirmation gate delayed, then a second false STOP two seconds later;
the runtime correctly marked the result unsuccessful and premature.

### Seed-1062 and final gate outcome

Seed 1062 exposed two remaining geometry defects. The first implementation
subtracted a non-paper 1 m standoff and forced a minimum 0.5 m hop, which could
exceed a 0.249 m bearing gate. After removing it, the verifier still compared
Euclidean slant distance with the paper's camera-forward `d_f`; valid off-axis
goals were rejected. Both contracts now match the paper and have focused
regression tests.

With the geometry corrected, seed 1062 still failed: exact replay found 0/89
target-visible decision frames, a false historical acquisition at 25.2 s, 29
LOST recoveries, and a final distance of 85.82 m. Seed 1060 and seed 1062 are
therefore two final-profile failures. The locked 4/5 gate is mathematically
impossible, so seeds 1063-1064 are not spent. C5 OnFly — Qwen3-VL 8B is
**mechanism-valid but model-rejected** in this local simulator. PMR may proceed
next; OnFly may be reopened only for a more capable compatible backend or the
authors' native release.
