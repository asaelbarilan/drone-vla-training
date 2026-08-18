# Experimental protocol

## The scientific object

Not "the universally best UAV autonomy architecture", but

> A\* = f(task regime, semantic uncertainty, flight dynamics, compute budget, latency budget)

Everything below follows from that. In particular there is **no global
architecture score**: results form a Pareto surface, reported per task regime.

## The fifteen configurations

They are controlled mutations, not a Cartesian product. Each names the question
it answers, the result that would support it, and the result that would falsify
it — the last column is the one that matters, because a configuration that
cannot be falsified is not an experiment.

| ID | Configuration | Question | Supporting result | Falsifying result |
|---|---|---|---|---|
| C0 | Oracle goal → fixed planner | How much failure is due to semantic architecture rather than flight execution? | Very high SR: the substrate is competent | Low SR: fix the stack before any FM conclusion |
| C1 | LLM → predefined skills → planner | Is coarse bounded mission authority enough? | Competitive SR at a low call rate | Large failures on visually grounded tasks |
| C2 | VLM → waypoint → fixed planner | Does visual grounding justify waypoint authority? | Better grounding than C1, no big safety/latency cost | No meaningful gain over skills |
| C3 | C2 + semantic/geometric verifier | Does explicit validation help beyond the planner? | Fewer invalid targets, modest SR gain | Negligible change; fix the verifier off later |
| C4 | C3 + periodic monitor, short context | Does supervision matter independently of memory? | Fewer overshoots, wrong stops, lost tasks | Same completion as C3 |
| C5 | C4 + compact keyframe memory | Does historical state specifically improve monitoring? | Better long-horizon completion and stopping | No gain, or unacceptable latency/memory cost |
| C6 | C3 + event-triggered recovery reasoner | Can reasoning be absent during nominal execution? | Similar/better hard-case SR with far fewer calls | Recovery success falls despite lower compute |
| C7 | Direct VLA, single action | Can learned control eliminate waypoint planning? | Better fine control/efficiency, acceptable safety | Strong safety or generalisation degradation |
| C8 | C7 + independent safety shield | Is a VLA's safety weakness separable from its control capability? | Collision reduction, little task penalty | Shield rewrites everything and destroys efficiency |
| C9 | C8 + compact history | Does a direct VLA need explicit semantic history? | Better long-horizon completion | No change despite extra compute |
| C10 | Periodic slow reasoner → VLA → shield | Does hierarchical reasoning help a direct VLA? | Gains on ambiguity and multi-stage tasks | Performance similar to C8 |
| C11 | C10 with chunked executor | Can a short action horizon bridge slow inference? | Smoother control, fewer semantic calls | More stale-action failures |
| C12 | Async streaming reasoner → chunked VLA → shield | Is non-blocking better than periodic hierarchy? | Lower delay/stalls at similar or better SR | Staleness offsets the concurrency gain |
| C13 | Event-triggered reasoner → VLA → shield | Should reasoning be invoked only on uncertainty/no progress? | Similar/better hard-case SR, sharply fewer calls | Trigger misses important semantic corrections |
| C14 | Predictive world-model VLA | Does explicit future-state prediction justify its complexity? | Targeted gains under occlusion/viewpoint change | No gain in exactly those regimes |

The eight **sentinels** to prove modularity first: C1, C2, C3, C5, C6, C7, C8, C12.
Between them they exercise every axis.

## Benchmark regimes

Results are always reported per regime. Pooling them would average over the very
thing the study claims varies.

| Regime | Config | What it tests |
|---|---|---|
| Long-horizon language navigation | `grid_nav` | Grounding, progress, stopping correctness, memory |
| Open-set object/goal search | `object_search` | Semantic exploration, target commitment, decoy resistance |
| Failure / ambiguity / recovery | `failure_recovery` | Blocked route, wrong target, sensing dropout, stale decisions |
| Fine continuous manoeuvring | `fine_maneuver` | Control authority, reaction frequency, action horizon |
| Partial observability *(optional)* | `occlusion` | Occlusion and viewpoint-change sensitivity |

## Staging

Run in this order. The ordering is part of the method, not a convenience.

```bash
uavlab sweep --experiment macro_screen      # 1. is authority level worth pursuing? is C0 sound?
uavlab sweep --experiment safety_screen     # 2. verifier (C2→C3) vs shield (C7→C8), separately
uavlab sweep --experiment timing_recovery   # 3. C3/C4/C6 and C8/C10/C12/C13
uavlab sweep --experiment memory_horizon    # 4. C4→C5, C8→C9, C10→C11
uavlab sweep --experiment predictive_state  # 5. C12 vs C14, only if occlusion still hurts
```

**Stop at stage 1 if C0 fails.** A weak control ceiling means the planner,
controller or environment is the problem, and every architecture number measured
in that environment is uninterpretable until it is fixed. The test
`test_the_oracle_control_ceiling_reaches_the_goal` encodes this as a hard gate.

Deployment optimisation — shared ViT features, KV caching, quantisation,
TensorRT, model scaling — comes **only** after the two or three Pareto-winning
stacks are known. Doing it earlier confounds functional architecture with
implementation efficiency.

## Interactions worth the compute

Cheaper than a full grid and where the real answers live:

- **Authority × safety boundary.** A waypoint planner and a direct VLA expose
  different physical authority; the safety boundary alone can dominate collision
  results. Never compare a shielded waypoint stack against an unshielded VLA and
  attribute the difference to "modularity".
- **Reasoning schedule × recovery policy.** Persistent low-rate monitoring and
  selective invocation are *competing hypotheses*, not interchangeable labels.
- **Memory × monitoring.** Long-term history may matter far more for "am I still
  accomplishing the mission?" than for instantaneous steering.
- **Action horizon × semantic refresh.** Longer chunks bridge slow reasoning and
  simultaneously make stale intent persist longer.
- **Async reasoning × decision staleness.** Non-blocking inference only helps
  while late outputs are still useful.

## Metrics

Two vectors, never collapsed into one number.

**Capability** — success, collision/safety-violation rate, correct terminal stop,
recovery success (scored only where recovery was attempted), subgoal completion,
path efficiency, executable-plan rate, false-target commitment.

**Cost** — median and p95 semantic latency, actual control-update frequency,
decision age at execution, stale-action rate, rejected/modified proposal rate,
reasoner calls and tokens, peak RSS.

`uavlab sweep` prints a per-regime table, the Pareto frontier with the dominating
architecture named for each dominated point, and paired-by-seed bootstrap
contrasts. Comparisons are paired because the same seed is the same scene;
unpaired means across random scenes would read scene difficulty as architecture
effect.

## Reproducibility

Every run writes `manifest.json`: git SHA, **dirty-tree flag**, architecture
config hash, full architecture and environment configs, seeds, Python and
platform, and a dependency hash. `uavlab replay RUN_DIR` re-runs from that
manifest and reports metric drift.

The dirty-tree flag matters as much as the commit. A result produced from
uncommitted edits is not reproducible, and recording that is the difference
between a caveat and a false claim.

## What the current numbers are and are not

The shipped policies are **simulated stand-ins**. They reproduce each family's
information flow, authority boundary and cost structure with scripted logic and a
configured latency budget drawn to bracket published ranges. Running the sweeps
today validates that the runtime is modular, deterministic, fair and correctly
instrumented.

It does **not** produce results about TypeFly, OnFly, CognitiveDrone, FLIGHT,
AeroVLA, PMR or any other system, and no table generated from these plugins
should be presented as such. Real model adapters replace one plugin each
(Milestone D) and change nothing else in the runtime — which is the point.
