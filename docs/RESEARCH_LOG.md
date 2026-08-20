# Research log — decision register

**What this is.** Every design decision taken in this testbed, why it was taken,
what evidence supports it, and what was rejected. It exists so that someone who
was not here — a reader, a reviewer, a supervisor, another agent — can reconstruct
how the results came to be, and so that a claim in the paper can be traced to the
measurement that justifies it.

**What this is not.** Not a changelog. `CHANGES.md` is the chronological record
of what was done when; this is the organised record of *what was decided and on
what grounds*. When the two disagree, this file is the one to correct.

## How to read an entry

Every decision has a stable identifier (`D-01`, `D-02`, …) that never changes and
is never reused. Entries are grouped by area, not by date, because the question a
reader has is "why is the search like this?", not "what happened on Tuesday".

| field | meaning |
|---|---|
| **Decision** | what is true in the code now |
| **Rationale** | why, in one or two sentences |
| **Evidence** | the measurement. "None" is a legitimate and important value |
| **Rejected** | what else was considered, and why it lost |
| **Status** | `settled` / `provisional` / `open` / `superseded by D-nn` |
| **Related work** | the paper this follows or departs from |

**Status discipline.** `settled` means measured and unlikely to change.
`provisional` means it works but the evidence is thin. `open` means it is known
to be wrong or unjustified and is waiting on work. A decision with no evidence
is `provisional` at best, however obviously correct it seems.

---

## A. Experiment structure

### D-01 — Architectures are configuration, not code
**Decision.** Every architecture is a YAML file composing the same plugin set.
There are no per-architecture code paths.
**Rationale.** A comparison between two architectures is only interpretable if
everything except the named difference is held identical, and forks drift.
**Evidence.** `test_c7_and_c8_use_an_identical_policy` asserts C7 and C8 differ
in the shield and nothing else.
**Rejected.** Subclassing per architecture — the standard approach, and the one
that makes "is this difference real or incidental?" unanswerable.
**Status.** settled.

### D-02 — Seven families, one base each, everything else an ablation
**Decision.** `ArchitectureConfig` carries `family` and `ablation_of`.
`validate_family_set` enforces exactly one base per family and requires every
other member to name what it modifies. `uavlab families` prints it.
**Rationale.** The families are the design space; the configs are points in it.
Without the constraint the set drifts into "N architectures" with no statement of
what varies — which had already happened: `direct_vla` held ten of fifteen
members while other families held one.
**Evidence.** The rule caught a real fault immediately: `ablation_of` inherits
through `_base_`, so declaring C7 an ablation of C8 made C8 an ablation of
itself.
**Rejected.** Keeping the structure in prose. It had been in prose and had
already drifted.
**Status.** settled.

### D-03 — C8 is the direct-VLA base, not C7
**Decision.** The shielded VLA is the family base; C7 is "remove the shield".
**Rationale.** Shipping a learned policy with no safety shield is the ablation,
not the default.
**Evidence.** None — a judgement about what the default *should* be.
**Status.** settled.

### D-04 — C12 is the hierarchy base, not C10
**Decision.** A concurrent reasoner over chunked actions is the base; C10 is
"make it blocking and single-step".
**Rationale.** That is the shape the literature describes.
**Related work.** CognitiveDrone-R1; LiteVLA-H (dual-rate, K=3 with event
override).
**Status.** settled.

### D-05 — Held-out seeds, enforced in code
**Decision.** `EVAL_SEEDS = 1..40` held out, `TRAIN_SEEDS = 1000..1999` the only
range data collection may draw from. `collect()` raises if a range crosses.
**Rationale.** Scenes are generated from the seed, so the seed is the unit of
separation. Splitting frames instead would put neighbouring frames of one flight
on both sides and report a fictional score.
**Evidence.** The split was already clean by default before it was enforced;
enforcement prevents drift rather than fixing a leak.
**Status.** settled.

---

## B. Runtime and fairness

### D-06 — A virtual simulation clock, with model latency charged to it
**Decision.** A model that takes 1.7 s per call costs 1.7 s of *simulated* time.
**Rationale.** Otherwise a slow architecture is compared against a fast one as
though inference were free, and every latency finding disappears.
**Status.** settled.

### D-07 — Latency is charged as a fixed constant, not measured wall time
**Decision.** `charge_mode: fixed` is the default.
**Rationale.** Charging live jitter to the simulation clock destroys
paired-by-seed comparison.
**Evidence.** Measured: two runs of the same seed diverge under `measured`.
Quantising the charge — the intuitive fix — also failed to reproduce; only a
fixed charge does.
**Rejected.** `quantised`, on measurement, having been the first thing tried.
**Status.** settled.

### D-08 — Decision age is a first-class metric, distinct from inference latency
**Decision.** `execution_sim_time − source_observation_sim_time` is recorded per
command.
**Rationale.** How obsolete the world was when a command landed is the quantity
that architecture timing actually changes; inference latency is only one input to
it.
**Status.** settled.

### D-09 — Search timing is clock-based, never per-decision
**Decision.** The search heading advances on simulated time.
**Rationale.** If it advanced per decision, a 10 Hz executor would sweep ten
times faster than a 1 Hz skill agent, and the authority comparison would be
contaminated by an exploration-rate difference nobody chose.
**Status.** settled. See D-14 for the value, which was wrong for years of this
project's short life.

---

## C. Search and exploration

### D-10 — Anchored outward spiral rather than a body-relative offset
**Decision.** The search pattern is anchored at launch with a growing radius.
**Rationale.** Offsetting from the current position each tick produces a circle
around wherever the vehicle happens to be: it turns continuously, never gets
further from home, and searches nothing.
**Status.** settled.

### D-11 — Boustrophedon sweep available, not default
**Decision.** `search_pattern: sweep` exists; `spiral` remains the default.
**Rationale.** Coverage planning is the right tool for *known* extent and is
provably complete where frontier search is complete only in unbounded time — but
it has to earn the default on measurement.
**Evidence.** It did not. c2 acquired the target in 0 of 104 belief queries under
spiral *and* under sweep at every lane spacing from 25.5 m to 4.8 m.
**Related work.** Choset & Pignon, boustrophedon cellular decomposition;
`drone_control/docs/coverage_vs_frontier.md`, which reached the same conclusion
from measurement on a different airframe.
**Status.** provisional — measured against a broken search (D-14) and worth
re-testing now that the search works.

### D-12 — Lane pitch derived from a forward wedge, not a sensor disc
**Decision.** Pitch is the view width at half sensor range.
**Rationale.** `drone_control` treats the sensor as a disc, giving a swath either
side of track. Here the camera is body-fixed and looks *along* the lane, so a
pass covers a forward wedge and the disc formula would overstate coverage.
**Status.** provisional — the sweep it serves is not in use.

### D-13 — `search_altitude_m` exists and defaults to off
**Decision.** The search may be flown at a stated altitude; by default it is not.
**Rationale.** Sight lines can be bought with altitude, at the cost of approach
time. That is a real architectural trade and deserves a knob.
**Evidence.** `grid_nav` obstacles top out at 11.1 m, the mission permits 25 m,
and the vehicle searched at 3.0 m — below every obstacle, with the target at
2.9 m, so sight lines crossed towers. At 20 m, acquisition on seed 3 went from
0/104 to 8/23. But over seeds 1–8 it scored 0.00 against the baseline's 0.62,
because acquiring from 18 m means descending through the obstacle field and C2
carries no shield.
**Status.** provisional — mechanism confirmed, net effect negative, needs a
descent plan before it can help.

### D-14 — The search dwell is derived, not chosen
**Decision.** `explore_dwell_s` defaults to 0, meaning derive it: chord length
between consecutive search points over the speed the mission permits.
**Rationale.** A search leg must be long enough to fly. The heading turns 50° per
leg, so consecutive points sit a chord apart — 45.6 m at the geofence radius,
9.1 s at 5 m/s. It was a fixed **3.0 s**.
**Evidence.** The single largest defect found in the project. Instrumented on c2,
seed 3: the search commanded points up to 54 m from launch while the vehicle
never exceeded **21.5 m** and oscillated between 6 and 21 m for the whole
episode. It was chasing a point that outran it. Fixing it, on 40 seeds never
looked at during the diagnosis: c1 0.45→0.70, c2 0.70→0.95, c3 0.60→0.97,
c6 0.60→0.95, c8 0.55→0.93. C0 reads ground truth and never explores, and did
not move — the control that shows the fix touched only the search.
**Rejected.** Advancing the leg on arrival. It would work, but it makes leg
length depend on flight performance and so reintroduces the coupling D-09 exists
to prevent.
**Status.** settled.

### D-15 — Everything measured about C1–C6 before D-14 is suspect
**Decision.** Findings about the scripted-search family predating D-14 are to be
re-read, not cited.
**Rationale.** They were measured on a search that could not travel more than
21.5 m from launch.
**Affected.** The occlusion measurement (target in range 100 %, blocked 100 %)
was real but downstream — the vehicle was pinned behind the obstacle cluster
because it could not travel. D-11 and D-13 were both evaluated against it.
**Status.** open.

---

## D. Perception and the semantic boundary

### D-16 — A pixel is unprojected using the pose that took the frame
**Decision.** The waypoint is computed in **world** coordinates from
`ctx.observation`, the same packet the image came from.
**Rationale.** The vehicle keeps flying while a model thinks — 1.7 s for Gemma
3 4B, metres of travel. A pixel is meaningless without the pose it was seen
from; a world point from the capture pose stays valid however far the vehicle has
since moved.
**Evidence.** `test_the_waypoint_is_unprojected_from_the_pose_that_took_the_frame`.
Pinned because the failure would be silent: the same pixel read against the
current pose still yields a plausible waypoint, just the wrong one, with the
error growing with model latency and looking like a model-quality problem.
**Status.** settled.

### D-17 — Depth is guessed, not measured
**Decision.** The unprojection places the waypoint at a fixed hop distance along
the ray (`hop_m`, or `arrival_hop_m` on arrival).
**Rationale.** A monocular pixel carries no range, and the testbed has no depth
sensor wired to the semantic path.
**Evidence.** None. This is the largest known inaccuracy in the waypoint family
and has never been quantified.
**Status.** open — the error should be measured against ground-truth range before
any C2-family result is presented.

### D-18 — Detections are gated by range, field of view and occlusion
**Decision.** The environment filters semantic hits by all three.
**Rationale.** Without it an architecture can succeed on information it never
observed, and memory would have nothing to be *for*.
**Status.** settled.

### D-19 — Frames are namespaced per episode and the store is cleared on reset
**Decision.** Frame URIs use a monotonic counter, not `id(env)`.
**Rationale.** `id()` is an address CPython recycles, and the frame store is
process-global.
**Evidence.** A new episode could resolve a reference to the previous episode's
pixels. It surfaced as c2g failing determinism by 1.4 mm, reproducibly. Only c2g
showed it, because C2 maps the emitted pixel straight to a waypoint with nothing
downstream to absorb a one-frame difference.
**Status.** settled.

---

## E. Memory and supervision

### D-20 — Memory carries identity, not just position and score
**Decision.** `MemoryItem.label`, and `recall_target` filters by it.
**Rationale.** Retrieval by salience alone returns whichever landmark was seen
closest and largest, so a nearby distractor beats the true target every time.
**Evidence.** Observed: the vehicle flew confidently to a distractor while every
component reported success.
**Status.** settled.

### D-21 — A real-model policy recalls only its own sightings
**Decision.** The policy's committed waypoint is stored under `kind="decision"`,
and the Gemma policy recalls with `kinds={"decision"}`.
**Rationale.** Memory stores are fed from `perception.detections` — the simulated
detector. A Gemma configuration that reads the detector through memory would have
its "memory result" be a detector result, in a family whose premise is that a
real model is the perceiver.
**Evidence.** Before: stripping memory changed c5g's trajectory on **0 of 8**
seeds while changing the scripted c5 on 3 of 10. After: 3 of 3.
**Status.** settled.

### D-22 — A decision taken from memory is never written back to memory
**Decision.** Envelopes marked `from_memory` are not recorded as sightings.
**Rationale.** Otherwise recall refreshes its own timestamp every tick, no
staleness bound can fire, and the policy orbits a position the model has not
confirmed.
**Evidence.** It did exactly that: c5g flew 9–17 m in a 60 s episode against
113–115 m with no memory, and adding an age limit changed *nothing at all* until
this rule existed.
**Status.** settled.

---

## F. Learned policy

### D-23 — Per-dimension action bins, not a joint codebook
**Decision.** Four independent 64-bin classifiers over (vx, vy, vz, yaw_rate).
**Rationale.** A joint codebook over a 4-D action space needs exponentially many
prototypes.
**Evidence.** Measured: K=1024 joint was *worse* than 16 per-dimension bins.
64 bins per dimension gives 0.065 m/s quantisation error.
**Rejected.** The joint codebook, which was my recommendation until measured.
**Status.** settled.

### D-24 — The policy is not given its own velocity
**Decision.** Proprioception is restricted to cos/sin of yaw.
**Rationale.** Causal confusion: velocity is a lagged copy of the previous
command.
**Evidence.** `corr(own velocity, expert action) = 0.92`. Given it, the network
learned the shortcut and nothing else — it scored 1.307 m/s where *echoing your
own velocity* scores 1.174, and froze at 0.12 m/s from a standing start.
**Related work.** de Haan et al. 2019; Wen et al. 2020 (copycat problem).
**Status.** settled.

### D-25 — Yaw comes from a rule, not from the network
**Decision.** `yaw_mode: course_aligned` points the nose along the commanded
velocity.
**Rationale.** Yaw is the one channel the teacher cannot convey through a single
frame, because its yaw command depends on a waypoint committed earlier.
**Evidence.** The network's yaw error was 0.319 against 0.294 for the best
possible *constant* — worse than never turning — while beating any constant by
2.5× on vx/vy. Left in the loop it was fatal: a body-fixed camera that never
turns loses the target and never recovers.
**Status.** settled.

### D-26 — A dilated frame history, not consecutive frames
**Decision.** `FRAME_OFFSETS = (0, 5, 15, 40)` — 0, 0.5, 1.5 and 4.0 seconds.
**Rationale.** Four consecutive stored samples span 0.3 s: enough to see motion,
far too short to remember where a target was last seen.
**Evidence.** Fixed stopping decisively — false stops fell from 24 of 40 episodes
to 1, stop precision 0.44 → 0.95. Did **not** fix navigation.
**Status.** settled for what it does; the navigation problem is D-27.

### D-27 — The behaviour-cloned policy does not navigate
**Decision.** `c7t`/`c8t` are shipped as a working pipeline carrying a policy
that does not work, and their numbers must not be read as an architecture result.
**Evidence.** Success 0.03 on held-out seeds after three interventions, each of
which fixed its measured defect and none of which was the binding constraint:
teacher swap (C0→C2), DAgger, frame stack. Reached-goal sat at 0.03–0.05
throughout.
**Related work.** GRaD-Nav++ and Exp2VLA both generate their own expert data in
simulation, which is the path being followed; no small off-the-shelf aerial VLA
exists to drop in, because small VLAs exist where manipulation datasets exist.
**Status.** open — parked deliberately, not abandoned.

---

## G. Verification and tooling

### D-28 — Verification checks that components *fire*, and that is not enough
**Decision.** `uavlab verify` asserts each architecture's distinguishing
component actually acts.
**Evidence of its limit.** C4G and C5G passed honestly while being behaviourally
identical to C3G: the monitor ran, memory updated, tokens were spent, and not one
metric of motion differed. Firing is not influencing.
**Status.** open — the check should compare against the same architecture with
the component removed and require the trajectory to differ. D-21 fixed the
particular case; the gate is still weak.

### D-29 — Runs are rendered to video, and video is not evidence of rate
**Decision.** `uavlab video` renders a plan view beside the camera frame.
Rendering is forced on for every architecture.
**Rationale.** A summary cannot say whether a run flew sensibly and stopped a
metre short or spiralled into a wall and got lucky. The camera panel separates a
perception failure from a policy failure.
**Evidence.** Enabling rendering leaves trajectories bit-identical on
c0/c4/c9/c13, so the video shows the episode that was scored.
**Caveat, learned the hard way.** A video is one seed. Excellent for seeing *how*
a run fails, worthless for *how often* — and it was used for the second, which
produced the false claim that C1–C6 never acquire the target.
**Status.** settled.

### D-30 — End maps are the debugging tool
**Decision.** A grid of final plan views across architectures × seeds.
**Evidence.** It found D-14, which months of summary metrics had not: the closed
loop was obvious at a glance and invisible in a success rate.
**Status.** settled.

---

## H. Open questions, ranked

| # | question | why it matters | first step |
|---|---|---|---|
| 1 | Why is C12 at 0.62 when C8 is at 0.93? | The hierarchy is *worse* than the VLA it is built on — the largest unexplained gap in the set | End maps of C12 vs C8 on the 15 seeds C12 times out on |
| 2 | Why does C0, with ground truth, fail seed 10 at 12 m? | The control ceiling is not a ceiling; it fails on collisions and now scores below C2, C3 and C6 | Video of `seed10/c0.mp4`, already rendered |
| 3 | How large is the depth-guess error (D-17)? | Unquantified inaccuracy under every waypoint-family result | Compare unprojected range against ground truth per decision |
| 4 | Do C3 and C6 differ at all? | They were identical on 18 of 20 seeds pre-D-14; `selective_recovery` may have no behaviour of its own | Re-measure post-D-14, then instrument trigger firings |
| 5 | Does the sweep (D-11) beat the spiral now? | It was rejected on evidence gathered against a broken search | Re-run the D-11 comparison |
| 6 | Can the cloned policy be made to navigate (D-27)? | The direct-VLA family currently has no learned member that works | Clone a non-privileged expert, or give the student a recurrent state |

---

## Superseded and corrected claims

Kept because a reader who finds the old claim elsewhere needs to know it was
withdrawn, and because the pattern of error is itself informative.

| claim | status | what was actually true |
|---|---|---|
| "C1–C6 orbit and never acquire the target" | **withdrawn** | True of seed 3, false of the regime. c2 succeeded on 14 of 20 seeds at the time. Generalised from one rendered video |
| "C2G's nondeterminism is intermittent GPU noise" | **withdrawn** | Deterministic and structural — a recycled `id()` in the frame store (D-19) |
| "C1–C6's failure is a search-pattern defect" | **partly withdrawn** | The field-of-view gap is real but does not decide the outcome; occlusion did, and behind that the dwell (D-14) |
| "c8 fails by arriving and not stopping" | **withdrawn** | Its 1.7 m median mixed successes with failures. No failure across 140 episodes ended within 5 m |
| "C2 has no memory, so it is an imitable teacher" | **withdrawn** | It has no memory *plugin*, but decides at 2 Hz and controls at 20 Hz, so 9 of 10 labels come from a planner tracking an earlier waypoint |
| "The joint action codebook is the right encoding" | **withdrawn** | Per-dimension bins measured 7× better (D-23) |
