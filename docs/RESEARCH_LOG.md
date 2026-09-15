# Research log — decision register

> **Read this first.** Every architecture number in this repository comes from a
> hand-written scripted policy. The one learned network does not navigate
> (D-27); no Gemma configuration completes a mission. The decisions below are
> real and measured, but they are decisions about a *harness*, not yet findings
> about foundation-model autonomy.

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
| **When** | date, time and the commit that carries it |
| **Decision** | what is true in the code now |
| **Rationale** | why, in one or two sentences |
| **Evidence** | the measurement. "None" is a legitimate and important value |
| **Rejected** | what else was considered, and why it lost |
| **Status** | `settled` / `provisional` / `open` / `superseded by D-nn` |
| **Related work** | the paper this follows or departs from |

**On the timestamps.** They are taken from git commit times, not written by
hand, so they are the moment a decision entered the repository rather than the
moment it was thought of — usually minutes apart, occasionally longer. Fifteen
entries predate version control (the testbed was built before `git init` on
2026-08-18 15:03) and cannot be dated individually; they say so rather than
carrying an invented time. Times are local to the machine the work was done on.

**Status discipline.** `settled` means measured and unlikely to change.
`provisional` means it works but the evidence is thin. `open` means it is known
to be wrong or unjustified and is waiting on work. A decision with no evidence
is `provisional` at best, however obviously correct it seems.

---

## A. Experiment structure

### D-01 — Architectures are configuration, not code
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
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
**When.** 2026-08-20 10:46 — `e7a78e5`
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
**Status.** superseded by D-41. The structural enforcement remains; the
top-level count and hierarchy placement changed.

### D-03 — C8 is the direct-VLA base, not C7
**When.** 2026-08-20 10:46 — `e7a78e5`
**Decision.** The shielded VLA is the family base; C7 is "remove the shield".
**Rationale.** Shipping a learned policy with no safety shield is the ablation,
not the default.
**Evidence.** None — a judgement about what the default *should* be.
**Status.** settled.

### D-04 — C12 is the hierarchy base, not C10
**When.** 2026-08-20 10:46 — `e7a78e5`
**Decision.** A concurrent reasoner over chunked actions is the base; C10 is
"make it blocking and single-step".
**Rationale.** That is the shape the literature describes.
**Related work.** CognitiveDrone-R1; LiteVLA-H (dual-rate, K=3 with event
override).
**Status.** settled.

### D-05 — Held-out seeds, enforced in code
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
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
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** A model that takes 1.7 s per call costs 1.7 s of *simulated* time.
**Rationale.** Otherwise a slow architecture is compared against a fast one as
though inference were free, and every latency finding disappears.
**Status.** settled.

### D-07 — Latency is charged as a fixed constant, not measured wall time
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** `charge_mode: fixed` is the default.
**Rationale.** Charging live jitter to the simulation clock destroys
paired-by-seed comparison.
**Evidence.** Measured: two runs of the same seed diverge under `measured`.
Quantising the charge — the intuitive fix — also failed to reproduce; only a
fixed charge does.
**Rejected.** `quantised`, on measurement, having been the first thing tried.
**Status.** settled.

### D-08 — Decision age is a first-class metric, distinct from inference latency
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** `execution_sim_time − source_observation_sim_time` is recorded per
command.
**Rationale.** How obsolete the world was when a command landed is the quantity
that architecture timing actually changes; inference latency is only one input to
it.
**Status.** settled.

### D-09 — Search timing is clock-based, never per-decision
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** The search heading advances on simulated time.
**Rationale.** If it advanced per decision, a 10 Hz executor would sweep ten
times faster than a 1 Hz skill agent, and the authority comparison would be
contaminated by an exploration-rate difference nobody chose.
**Status.** settled — but see D-14: the *principle* was right and the value it
was given was the single largest defect in the testbed.

---

## C. Search and exploration

### D-10 — Anchored outward spiral rather than a body-relative offset
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** The search pattern is anchored at launch with a growing radius.
**Rationale.** Offsetting from the current position each tick produces a circle
around wherever the vehicle happens to be: it turns continuously, never gets
further from home, and searches nothing.
**Status.** settled.

### D-11 — Boustrophedon sweep available, not default
**When.** 2026-08-19 22:22 — `a8254d3`
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
**When.** 2026-08-19 22:22 — `a8254d3`
**Decision.** Pitch is the view width at half sensor range.
**Rationale.** `drone_control` treats the sensor as a disc, giving a swath either
side of track. Here the camera is body-fixed and looks *along* the lane, so a
pass covers a forward wedge and the disc formula would overstate coverage.
**Status.** provisional — the sweep it serves is not in use.

### D-13 — `search_altitude_m` exists and defaults to off
**When.** 2026-08-19 22:43 — `19bbc9b`
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
**When.** 2026-08-20 12:52 — `4806427`
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
**When.** 2026-08-20 12:52 — `4806427`
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
**When.** 2026-08-20 13:59 — `ed5ae2f`
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
**When.** 2026-08-20 13:59 — `ed5ae2f`
**Decision.** The unprojection places the waypoint at a fixed hop distance along
the ray (`hop_m`, or `arrival_hop_m` on arrival).
**Rationale.** A monocular pixel carries no range, and the testbed has no depth
sensor wired to the semantic path.
**Evidence.** None. This is the largest known inaccuracy in the waypoint family
and has never been quantified.
**Status.** open — the error should be measured against ground-truth range before
any C2-family result is presented.

### D-18 — Detections are gated by range, field of view and occlusion
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** The environment filters semantic hits by all three.
**Rationale.** Without it an architecture can succeed on information it never
observed, and memory would have nothing to be *for*.
**Status.** settled.

### D-19 — Frames are namespaced per episode and the store is cleared on reset
**When.** 2026-08-18 22:09 — `43fe7e9`
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
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** `MemoryItem.label`, and `recall_target` filters by it.
**Rationale.** Retrieval by salience alone returns whichever landmark was seen
closest and largest, so a nearby distractor beats the true target every time.
**Evidence.** Observed: the vehicle flew confidently to a distractor while every
component reported success.
**Status.** settled.

### D-21 — A real-model policy recalls only its own sightings
**When.** 2026-08-19 21:18 — `abb1c24`
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
**When.** 2026-08-19 21:18 — `abb1c24`
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
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** Four independent 64-bin classifiers over (vx, vy, vz, yaw_rate).
**Rationale.** A joint codebook over a 4-D action space needs exponentially many
prototypes.
**Evidence.** Measured: K=1024 joint was *worse* than 16 per-dimension bins.
64 bins per dimension gives 0.065 m/s quantisation error.
**Rejected.** The joint codebook, which was my recommendation until measured.
**Status.** settled.

### D-24 — The policy is not given its own velocity
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** Proprioception is restricted to cos/sin of yaw.
**Rationale.** Causal confusion: velocity is a lagged copy of the previous
command.
**Evidence.** `corr(own velocity, expert action) = 0.92`. Given it, the network
learned the shortcut and nothing else — it scored 1.307 m/s where *echoing your
own velocity* scores 1.174, and froze at 0.12 m/s from a standing start.
**Related work.** de Haan et al. 2019; Wen et al. 2020 (copycat problem).
**Status.** settled.

### D-25 — Yaw comes from a rule, not from the network
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
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
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** `FRAME_OFFSETS = (0, 5, 15, 40)` — 0, 0.5, 1.5 and 4.0 seconds.
**Rationale.** Four consecutive stored samples span 0.3 s: enough to see motion,
far too short to remember where a target was last seen.
**Evidence.** Fixed stopping decisively — false stops fell from 24 of 40 episodes
to 1, stop precision 0.44 → 0.95. Did **not** fix navigation.
**Status.** settled for what it does; the navigation problem is D-27.

### D-27 — The behaviour-cloned policy does not navigate
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
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
**When.** on or before 2026-08-18 15:03 — predates version control, so not individually dated; first recorded in `903ed58`
**Decision.** `uavlab verify` asserts each architecture's distinguishing
component actually acts.
**Evidence of its limit.** C4G and C5G passed honestly while being behaviourally
identical to C3G: the monitor ran, memory updated, tokens were spent, and not one
metric of motion differed. Firing is not influencing.
**Status.** open — the check should compare against the same architecture with
the component removed and require the trajectory to differ. D-21 fixed the
particular case; the gate is still weak.

### D-29 — Runs are rendered to video, and video is not evidence of rate
**When.** 2026-08-19 21:39 — `e51c384`
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
**When.** 2026-08-19 21:55 — `d798d42`
**Decision.** A grid of final plan views across architectures × seeds.
**Evidence.** It found D-14, which months of summary metrics had not: the closed
loop was obvious at a glance and invisible in a success rate.
**Status.** settled.

### D-31 — C11 confounds two changes and is not a clean ablation
**When.** 2026-08-20 15:40 — investigation, no code change
**Decision.** Recorded as a defect, not yet fixed: `c11` changes the action
horizon *and* the policy implementation at the same time, so "what does chunking
cost?" is not currently answerable.
**Rationale.** C10 runs `mock_vla`; C11 runs `chunk_vla`. They are separate
implementations, not one policy under two horizons.
**Evidence.** Scoring the chain on seeds 101–140: c8 0.93, c10 0.82, **c11 0.57**,
c12 0.62 — the c10→c11 step is by far the largest. Splitting it: `chunk_vla` at
its shortest horizon scores 0.68 against `mock_vla`'s 0.82, so roughly 0.15 is
the policy swap and 0.11 the horizon. Neither number is trustworthy while both
move together.
**Related work.** The action-horizon question is the one C11 exists to answer,
and it is exactly what FLIGHT and ScoutVLA vary.
**Status.** open — the fix is for both to share one action law with the horizon
as the only difference.

### D-32 — The chunked policy does not turn, and naively making it turn is worse
**When.** 2026-08-20 15:40 — reverted, no code change
**Decision.** `chunk_vla` emits `yaw_rate_rps=0.0` for every action. Left as is.
**Rationale.** It looks like an oversight beside `mock_vla`, which computes a
yaw rate from the same belief.
**Evidence.** Giving `chunk_vla` the identical yaw law took C11 from 0.57 to
**0.00** and C12 from 0.62 to 0.00, and the change was reverted. A yaw rate is a
*rate*: `mock_vla` applies it for one 0.2 s step and then re-decides at 10 Hz,
whereas a chunk commits it open-loop for 0.8 s and the vehicle over-rotates past
its target heading with no feedback to stop it.
**Rejected.** The naive fix, on measurement. A correct one has to integrate the
heading error over the chunk rather than hold a rate.
**Note.** Measured on seed 103, C11 turns **0 degrees** across the episode and
still has the target in view 100% of ticks, so on that seed the zero yaw costs
nothing. Whatever C11 loses, it is not primarily perception.
**Status.** open.

### D-33 — Three explanations for the C11 gap, tested and rejected
**When.** 2026-08-20 15:40 — investigation, no code change
**Decision.** Recorded so they are not re-tried.
**Evidence.** On seeds 101–140 against C11's shipped 0.57: swapping the memory
plugin back to C8's `short_context` gives 0.57 (no effect); removing the in-chunk
velocity decay gives 0.62; raising cruise speed 3.0→4.0 m/s gives 0.62; every
chunk length from 1 to 8 stays between 0.53 and 0.68. Arrival, not stopping, is
what fails: C11 enters the goal radius on 23 of 40 against C8's 37, and on every
run where it arrives it declares done — **zero** arrived-but-never-stopped across
all four configurations.
**Status.** open — the mechanism is still unidentified.

---

## H. Open questions, ranked

| # | question | why it matters | first step |
|---|---|---|---|
| 1 | Why is C11 at 0.57 when C10 is at 0.82? | Localised to the c10→c11 step (D-31); three explanations rejected (D-33); C11 arrives on 23 of 40 against C8's 37 | Give `chunk_vla` and `mock_vla` one shared action law so the horizon is the only difference |
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
| D-118/D-119 history is runtime reconstruction; live35.95s history ends27.85s | **withdrawn, D-120** | Probe used dense control-cadence history. Actual event-ordered memory ends34.95s; current RGB/raw replies remain exact |
| "C1–C6 orbit and never acquire the target" | **withdrawn** | True of seed 3, false of the regime. c2 succeeded on 14 of 20 seeds at the time. Generalised from one rendered video |
| "C2G's nondeterminism is intermittent GPU noise" | **withdrawn** | Deterministic and structural — a recycled `id()` in the frame store (D-19) |
| "C1–C6's failure is a search-pattern defect" | **partly withdrawn** | The field-of-view gap is real but does not decide the outcome; occlusion did, and behind that the dwell (D-14) |
| "c8 fails by arriving and not stopping" | **withdrawn** | Its 1.7 m median mixed successes with failures. No failure across 140 episodes ended within 5 m |
| "C2 has no memory, so it is an imitable teacher" | **withdrawn** | It has no memory *plugin*, but decides at 2 Hz and controls at 20 Hz, so 9 of 10 labels come from a planner tracking an earlier waypoint |
| "The joint action codebook is the right encoding" | **withdrawn** | Per-dimension bins measured 7× better (D-23) |

---

## Chronological index

The same decisions in the order they were taken, for reading the project as a
diary rather than as a reference. Session boundaries are where the day changes.

### Before 2026-08-18 15:03 — initial build, pre-version-control
D-01 architectures as configuration · D-05 held-out seeds · D-06 virtual clock ·
D-07 fixed latency charging · D-08 decision age · D-09 clock-based search timing ·
D-10 anchored spiral · D-18 detection gating · D-20 memory carries identity ·
D-23 per-dimension action bins · D-24 velocity withheld from the policy ·
D-25 rule-based yaw · D-26 dilated frame history · D-27 cloned policy parked ·
D-28 verification checks components fire

### 2026-08-18 — verification and determinism
| time | | |
|---|---|---|
| 15:44 | `247cbb3` | verify all 22 configs; pin the Ollama sampling seed |
| 19:02 | `a3811f7` | C1's scan frequency stops masking its architecture result |
| 22:09 | `43fe7e9` | **D-19** frames namespaced per episode — the recycled `id()` leak |

### 2026-08-19 — looking at the runs
| time | | |
|---|---|---|
| 21:18 | `abb1c24` | **D-21, D-22** the Gemma policy recalls only its own sightings |
| 21:39 | `e51c384` | **D-29** episodes rendered to video |
| 21:55 | `d798d42` | **D-30** end maps; a camera for every architecture |
| 22:22 | `a8254d3` | **D-11, D-12** boustrophedon sweep ported — and rejected on measurement |
| 22:43 | `19bbc9b` | **D-13** search altitude; the claim that C1–C6 never acquire is withdrawn |

### 2026-08-20 — structure, baseline, and the defect
| time | | |
|---|---|---|
| 10:46 | `e7a78e5` | **D-02, D-03, D-04** seven families enforced in code |
| 10:51 | `87e7a99` | seven bases baselined over 20 seeds |
| 12:52 | `4806427` | **D-14, D-15** the search dwell was 3 s and needed 9.1 |
| 13:59 | `ed5ae2f` | **D-16, D-17** frame-to-pose binding pinned; depth guess recorded |

### D-34 — The camera model belongs in the runtime, not in a simulator adapter
**When.** 2026-08-20 16:35 — investigation while planning the AirSim port
**Decision.** `Camera` moved from `adapters/gym/render.py` to `core/camera.py`.
Adapters supply intrinsics through `ObservationPacket`; policies unproject with
them.
**Rationale.** A pinhole projection is not a property of one simulator. It is the
geometry that turns "the model pointed at that pixel" into a world point, and it
is the same arithmetic whether the pixels came from a rasteriser, from AirSim, or
from a real camera.
**Evidence.** The point-and-fly policy imported the *toy simulator's rendering
module* to do its own geometry, so it could not have run against any other
simulator. It was the only such leak in the runtime, and it was found by a
boundary test written while planning the port rather than by the port failing.
Round-trip project/unproject is exact to 0.0 px after the move; 233 tests pass.
**Status.** settled.

### D-35 — The runtime is simulator-agnostic; the tooling is not
**When.** 2026-08-20 16:35 — audit, pinned by tests
**Decision.** Two boundary tests. One asserts `core/` and `plugins/` mention no
concrete environment. The other pins the exact set of modules that *do* bind to
`DeterministicEnv`, so adding another is a deliberate act.
**Rationale.** "Simulators are adapters" is the central claim of the testbed and
had never been checked. If it is false, moving to AirSim is a rewrite rather than
a configuration change.
**Evidence.** The runtime is clean. Four modules are not: `training/dataset.py`,
`training/dagger.py`, `analysis/replay_video.py` (all monkeypatch
`DeterministicEnv.step`) and `adapters/dataset_replay/replay.py` (subclasses it,
by design). The consequence is concrete — on AirSim there would be no training
data, no DAgger and no video, which are the three things most needed when a port
misbehaves.
**Status.** open for the tooling; the fix is a recording hook on the environment
interface so tools subscribe rather than patch. TODO item 15.

### D-36 — AirSim is not worth porting to until a real model is in the loop
**When.** 2026-08-20 16:35 — planning decision
**Decision.** The AirSim benchmark waits on TODO items 1 and 2.
**Rationale.** AirSim's contribution is photorealistic imagery. The scripted
policies do not look at pixels at all — they read simulated detections — so
porting them buys cost and no information.
**Evidence.** None needed for the direction; the supporting facts are that every
current number comes from a scripted policy, and that the one learned network
scores 0.03.
**Status.** settled as a sequencing decision; revisit if a real-model
configuration starts completing missions.

### D-37 — Frame namespaces must be consumed, not reconstructed from object IDs
**When.** 2026-08-22 — post-D-14 training rerun
**Decision.** The local-simulator collector and DAgger now resolve the rendered
frame with `DeterministicEnv._frame_ns`, matching the URI emitted by the
environment. A regression test requires a successful rendered flight to produce
non-empty, aligned frame/action samples.
**Rationale.** D-19 correctly replaced recyclable `id(self)` frame namespaces
with a monotonic episode namespace, but the two training tools still rebuilt the
old URI. Successful expert flights therefore recorded zero frames.
**Evidence.** Before the fix, 8 successful flights in the first 25 episodes
produced 0 samples. After the fix, the same collection path produced 1,524
samples by episode 25 and completed with 22,025 samples. The focused collector
and contract suite passes.
**Status.** settled for the local simulator. D-35 remains open because the tools
still monkeypatch one concrete environment.

### D-38 — Experiment seeds are literal scene identities
**When.** 2026-08-22 — corrected Gemma screen
**Decision.** `ExperimentConfig.cells()` executes the exact seeds declared in
the experiment. `episodes_per_cell` is fixed at one; repetitions must be
represented by explicit additional seeds. Kept sweep logs now also persist each
full `EpisodeResult`.
**Rationale.** The seed is the scene identity and unit of pairing. An implicit
`seed * 1000 + rep` transform made the manifest claim seeds 1–3 while episodes
actually used 1000, 2000 and 3000; seed 1000 is inside the learned-policy
training range. The report was neither reproducible from its manifest nor a
held-out comparison.
**Evidence.** The invalid sweep printed 1000/2000/3000 and was stopped before
the real-model cells. Regression tests now pin exact cells and result-file
persistence; the corrected sweep printed and stored seeds 1/2/3.
**Status.** settled.

### D-39 — Fixing the search data does not rescue the cloned direct policy
**When.** 2026-08-22 — full local-simulator rerun
**Decision.** The post-D-14 behaviour-cloning checkpoint is retained as a
negative result, not promoted into the shipped C7T/C8T configs.
**Evidence.** C2 on `grid_nav_vision`, training seeds 1000–1249: 98/250
successful demonstrations, 22,025 samples, 0.83 GB. Compared with the previous
dataset, 28.2% versus 3.1% of actions are below 0.5 m/s. The 429,634-parameter
frame-stack policy trained for 20 epochs to 1.439 m/s validation velocity error
(0.075 m/s quantisation floor), stop recall 1.00 and precision 0.93. On held-out
seeds 1–40: C7T 0.00 success / 0.00 reached-goal / 0.625 collision; C8T 0.00
success / 0.025 reached-goal / 0.00 collision. The shield changes safety, not
capability.
**Rejected.** D-14's degenerate search data as the binding explanation for the
learned policy. Repeating the same behaviour-cloning recipe again is not the
next experiment.
**Status.** settled as a negative result; TODO item 1 remains open for a
different learning formulation.

### D-40 — Gemma grounds and can reach, but terminal proximity is ungrounded
**When.** 2026-08-22 — corrected local real-model screen
**Decision.** Keep the original Gemma prompt and fixed-hop waypoint policy. Do
not add renderer-specific colour segmentation or the tested target-scale stop
heuristic.
**Evidence.** Corrected held-out screen, seeds 1–3: C2 0.67 success, C2G 0.00,
C3G 0.00; every real-model episode timed out without collision. In a standalone
C2G seed-2 run, Gemma found the target on 14/22 calls with zero parse errors,
the vehicle entered the 2 m goal radius at 52.35 s, and Gemma never emitted
arrival; it ended 3.36 m away. Controlled clean frames showed Gemma answering
`arrived=false` even at 2 m. Asking for apparent target height looked monotonic
on clean frames but stopped the cluttered mission 27.6 m away, so it was
reverted. Qwen3-VL 2B consumed 512 reasoning tokens without emitting content;
Moondream reported arrival at every tested distance; SmolVLM did not follow the
JSON/pixel contract.
**Interpretation.** Gemma is functioning as a visual grounder; the missing
capability is monocular range/terminal-state estimation. A learned range head or
two-view geometry is a legitimate next component. A red-pixel rule would be a
local-renderer cheat and is explicitly rejected.
**Status.** open; TODO item 2.

### D-41 — One baseline plus five families; fast/slow is a hybrid subfamily
**When.** 2026-08-23 — taxonomy correction against the concise experiment design
**Decision.** The top-level comparison is C0 as the classical control baseline
plus five autonomy families: LLM tool planner, VLM semantic waypointer, hybrid
stack, selective recovery supervisor and direct VLA. `fast_slow_hierarchy` is
now an explicit subfamily of `hybrid_stack`. C12 remains the reference for that
subfamily, while C3 remains the primary hybrid representative.
**Rationale.** A slow reasoner over a fast executor is a composition and timing
choice inside a hybrid stack, not a distinct authority family. Treating it as a
seventh peer contradicted the concise experiment design and inflated a nested
variant into a headline comparison.
**Evidence.** `ArchitectureConfig` now separates `family` from `subfamily`;
`validate_family_set` enforces one primary base per top-level category and one
reference per named subfamily. C10–C14 declare `family: hybrid_stack` and
`subfamily: fast_slow_hierarchy`. The canonical local screen is C0/C1/C2/C3/C6/C8
and completed an end-to-end one-seed wiring smoke. Its scores are explicitly
not model results.
**Status.** settled as the benchmark taxonomy; model-validity gates remain open.

### D-42 — RGB-D closes the range channel, not the real-model capability gap
**When.** 2026-08-23 — local real-model terminal-range gate
**Decision.** Keep calibrated depth sampled at the VLM-grounded pixel, target
world-point consistency, and a second cropped VLM confirmation before terminal
stop. Share this profile across C2G–C6G. Reject depth or triangulation as
unverified steering authority, and do not expand the screen to 20 seeds while
the 1–3 seed capability gate is zero.
**Rationale.** Depth answers how far the pointed surface is; it cannot establish
that the surface is the mission target. A second semantic check is required to
avoid turning a nearby obstacle into a successful arrival. Vision and
non-vision variants must also retain the same 90 s task horizon; wall-clock cost
does not justify changing the mission.
**Evidence.** Two-view steering ended seed 2 at 50.5 m and active parallax at
36.7 m, so both were rejected. Depth-only world consistency stopped C2G seeds 1
and 3 prematurely at 24.77 m and 27.72 m. Cropped semantic confirmation removed
those false stops. The safe 3-seed gate scored C2 2/3 and C2G/C3G/C6G all 0/3;
C6G collided on one seed. On the corrected 90 s horizon C2G seed 2 entered the
goal at 62.65 s but never produced a valid terminal observation and finished
45.77 m away. Qwen3-VL 2B still consumed all output tokens as `thinking` with
Ollama's native `think:false` and emitted no content.
**Status.** range channel settled for RGB-D local simulation; real visual
grounding remains open under TODO item 2.

### D-43 — SUPER is the one shared waypoint-execution substrate
**When.** 2026-08-25 — primary paper and official-source audit
**Decision.** Replace `fixed_local` in C0/C1/C2/C3-C6 with one configuration-
selected SUPER-derived planner plugin. Reproduce the dual exploratory/known-
free-backup commitment mechanism; normalize LiDAR, CIRI/MINCO internals and
OMMPC to the local simulator's range-fan and frozen controller interfaces.
Direct VLA remains planner-free. The frozen fidelity record and gate are in
[`docs/fidelity/SUPER.md`](fidelity/SUPER.md).
**Rationale.** The current reactive bearing deflection has none of SUPER's
defining two-trajectory safety contract, so calling it a classical execution
ceiling would be paper-inaccurate. Running the official ROS stack beside the
testbed would also defeat the common contracts and make architecture comparison
unclean.
**Evidence.** Ren et al. (Science Robotics 2025) and official commit
`2ad3419c127a617c6d7df6925e81a14175a9c096` were inspected. Both generate an
exploratory path with unknown-as-free A*, a known-free stopping backup, and
retain the last committed trajectory when replanning fails or overruns.
**Result.** The independent `super_local` plugin now provides point-evidence
mapping, unknown-permissive A*, shortened corridor seeds, a known-free stopping
backup, start escape, prior-commitment retention and same-goal hot-start. C0,
C1 and C2 (therefore C3-C6) select it through YAML. Dev seeds 1000-1019 scored
20/20 on both `grid_nav` and `failure_recovery`, with zero collisions and zero
shield interventions; deterministic repeat passed. The complete suite reports
253 passed. Evidence: `reports/paper_implementation/super_gate.json`.
**Status.** accepted and frozen. Do not retune while implementing later papers.

### D-44 — AerialClaw is the first accepted real-model family member
**When.** 2026-08-25 — primary paper/source audit, implementation and frozen
development gate
**Decision.** C1 is a paper-faithful AerialClaw-style closed-loop
brain-skill-runtime agent, not the prior scripted skill policy. A real local
`gpt-oss:20b` emits one JSON-schema-constrained hard skill or terminal verdict;
`SkillRuntime`, the semantic endpoint verifier and shared SUPER own validated
execution. SOUL/BODY and task soft-skill Markdown, bounded reflection/feedback
history, explicit done evidence and fail-closed model behavior are required.
**Rationale.** AerialClaw's causal claim is incremental model composition of
validated skills. A fixed program that happens to call the same skills tests
only wiring. The official framework is model-agnostic and releases no trained
checkpoint, so the locally loadable 20.9B/3.6B-active gpt-oss profile is a
declared normalized current-best backend rather than a claimed paper weight.
**Evidence.** The paper, official repository commit
`e01adaa73c38fb10ec4bc5e8c0f71915cc7490a8` and release documentation were
audited. The final development gate (`reports/paper_implementation/
aerialclaw_gate.json`) scored grid navigation 5/5 and object search 5/5 on
seeds 1020-1024, with zero collisions, zero runtime errors and no privileged
input or fallback. Every run recorded real inference, typed model-authored
skills, verification and SUPER plans. Repeated grid seed 1020 matched success,
termination, typed sequence, exact arguments and final distance. Held-out seeds
1-40 were untouched. C1 config validation, changed-file Ruff, 78 focused tests
and the complete 280-test regression pass.
**Substrate audit.** Development found shared defects instead of papering them
over with a target script: duplicated active decisions evicted observations;
same-XY altitude goals collapsed in SUPER; random boxes violated the declared
ground-column sensor model; and endpoint validation confused route obstacles
plus the no-hit horizon sentinel with an invalid target. SUPER's frozen gate
was rerun after correction and stayed 40/40 with zero collisions/interventions.
Coverage options are frozen from launch pose and geometric range only; no
target coordinate or scoring truth enters C1.
**Status.** accepted and frozen. See `docs/fidelity/AerialClaw.md`. The next
paper implementation is See, Point, Fly; no later family is edited first.

### D-45 — SPF is integrated, but the local VLM capability gate is blocked
**When.** 2026-08-25 — primary paper/source audit, clean-room integration and
development-only real-model probes
**Decision.** Keep C2's paper-valid execution profile as the exact SPF causal
mechanism: current RGB plus instruction to strict `(u,v,distance)` output,
published nonlinear travel scaling, calibrated camera lift, typed waypoint and
shared SUPER execution. Do not reuse the legacy Gemma RGB-D arrival policy, add
a detector/range oracle, relax terminal scoring, or silently substitute a
script. C2 has no OnFly verifier; that mechanism begins at C3.
**Evidence.** The CoRL/PMLR paper, supplement and official repository commit
`5621bcf43e9826d60df014541dd0498e743a92bd` were audited. The repository is
proprietary, so the plugin is a clean-room implementation of the published
schema and equations. A 31-work evidence ledger validates the review. Focused
SPF/Ollama tests pass 11/11, changed-file Ruff passes, and the complete suite
passes 296 tests. Exact configuration IDs and the new `profile_of` relationship
let `c2` and `c2_spf` coexist without turning a backend profile into a second
family member. Frozen SUPER and AerialClaw gates were rerun and remain fully
passing.
**Backend audit.** On seed 1040 controlled frames, Gemma 3 4B produced the
wrong normalized point `(5,5)` even without constrained decoding; Qwen3-VL 2B
produced non-monotonic close-range labels; Gemma 4 e2b always emitted label 5;
Gemma 3 12B grounded better but emitted labels `6,4,4,3,4,3` from 30 m to 1.5 m
and never a near label. Qwen3-VL 8B was the only viable grounder. In closed
loop it entered the goal region at 64 s but its isolated labels 2 and 1 were not
consecutive, so it flew away and timed out. Single-label stopping terminated
4.77 m or 4.12 m away; a metric-range prompt lost the target and ended 91.12 m
away. Those variants were falsified and reverted. No held-out seed 1-40 was
used. Full evidence is in
`reports/paper_implementation/spf_backend_audit.json`.
**Status.** not accepted and not frozen. The same model/resource blocker has
survived all available compatible local backends. The minimum external action
is access to the paper's Gemini-class VLM or an open checkpoint that passes the
locked point/range probe. Sequential work remains at SPF; AeroVLA is not started.

### D-46 — AeroVLA mechanism is integrated; neither local profile is accepted
**When.** 2026-08-25 — primary paper/source audit and development-only real-model runs
**Decision.** Represent AeroVLA as C7/C8 profiles inside the common runtime:
one vertically mosaicked front/down image, target description, one of seven
coarse target-relative bearings, three 99-bin numerical actions, intrinsic
LAND, direct kinematic authority, and an optional independent C8 shield. No
planner, detector, depth stop, memory or scripted fallback may enter the policy.
This supersedes D-45's sequencing sentence after the user explicitly directed
work to continue past the externally blocked SPF backend.
**Evidence.** The full paper, official Apache-2.0 repository commit
`e37685afb8953d1f5a09155d7255960cee1bfd9d`, official 463 MB LoRA, 257 MB
training JSON and 15.1 GB OpenVLA-7B base listing were inspected. The released
executor uses yaw range `[-1.1,1.1]` although the paper says `[-pi,pi]`; the
executable source is locked and the discrepancy is logged. Focused tests cover
the codec, mosaic, NED/ENU conversion, direct route, intrinsic stop and C7/C8
shield isolation.
**Result.** Native BF16 requires the paper-reported 17 GB VRAM and does not fit
the local 8 GB RTX 4060. The fail-closed native profile is wired but its base is
not downloaded. The normalized Gemma profile ran real inference. After frame-
sign and prompt-contract corrections, seed 1060 emitted neutral `(49,49,49)`
on every one of 19 calls and timed out. Prompted or scripted steering was not
substituted.
**Status.** mechanism integrated; not accepted. See
`docs/research/AEROVLA_IMPLEMENTATION_LOCK.md` and
`reports/paper_implementation/aerovla_gate.json`.

### D-47 — OnFly maps to C3/C4/C5; normalized Gemma gate is closed
**When.** 2026-08-25 — primary paper audit, clean-room integration and sequential dev gate
**Decision.** Full OnFly is a composition in the existing testbed rather than a
new family or simulator fork. `c3_onfly_gemma` supplies image-point decision,
RGB-D lift, bearing gate, verifier and the shared planner. `c4_onfly_gemma` adds
the independent slow forced-choice visual monitor and a recent window.
`c5_onfly_gemma` changes only memory to first frame + four distance-segment
keyframes + latest frame. Gemma 3 4B is a normalized profile, not the paper's
Qwen3-VL-4B-AWQ checkpoint.
**Evidence.** The paper was inspected end to end. It specifies integer image
targets, previous-goal reprojection, CONTINUE/STOP/LOST monitoring every 2 s,
four keyframes, 7 m maximum depth, semantic/geometric verification and a
receding-horizon ESDF planner. It reports 67.8% SR and 2.7% CR, versus 35.8% SR
and 37.5% CR without the planner. The official repository still says `Code
coming soon`, so unavailable shared-ViT features, separate KV-cache mechanics,
exact prompts and Fast-Planner changes are explicitly normalized rather than
claimed reproduced. The 31-work evidence ledger remains valid.
**Implementation correction.** Two same-seed dry runs revealed that visual
deduplication first compared against the whole route and then against the
latest slot itself, collapsing memory to two frames. The final design keeps a
separate immutable candidate pool, applies feature deduplication only within a
3 m geometric neighborhood, and serializes initial/segment/latest frames. The
corrected seed 1060 run delivered 1-6 images to the monitor (mostly 4-5).
**Result.** Corrected dev seed 1060 timed out 25.71 m from goal; seed 1061 timed
out 18.17 m away. Both had zero collisions, zero inference/parse errors, 33
decision calls and 21 monitor calls; every monitor verdict was CONTINUE. Two
failures make the frozen 4/5 acceptance gate impossible, so seeds 1062-1064
were not spent. Held-out seeds 1-40 remain untouched.
**Status.** mechanism integrated; normalized Gemma profile not accepted. Do
not add scripted pixels, target coordinates or steering. Reopen only for a
capable backend/native release. See `docs/research/ONFLY_IMPLEMENTATION_LOCK.md`
and `reports/paper_implementation/onfly_gate.json`. All changed implementation
files pass Ruff and the complete regression passes 321 tests.

### D-48 — Qwen proves the OnFly mechanism once; semantic gate still rejects the profile
**When.** 2026-08-26 — exact replay, sequential local Qwen gate
**Decision.** Keep the Qwen3-VL 8B OnFly profile as a declared real-model
implementation, but reject it from the benchmark representative set. Do not
repair it with scripted search, a color detector, target coordinates, or
simulator truth. The next paper system may proceed because the 4/5 OnFly gate
is now conclusively closed rather than merely unfinished.
**Evidence.** The 0--999 Qwen coordinate adapter passed its six-frame offline
gate. Scheduler start-to-start deadlines, execution-time source expiry,
persistent acquisition memory, and paper-defined last-normal-yaw recovery were
implemented. Correcting recovery from “face the old position” to “restore the
old heading” changed seed 1061 from repeated timeouts to a correct stop 1.606 m
from the goal at 69.2 s, with zero collision and exact replay error 0.0 m.
Seed 1060 then exposed reproducible confusion of a green tower-like distractor
with the requested red tower. A generic named-attribute prompt corrected one
frame but not the independent historical false positive. Qwen3-VL 2B and
Qwen3.5 2B failed the same negative/positive offline gate. The final-profile
seed-1060 rerun ended on two confirmed false STOPs at 28.41 m after 15.2 s;
exact replay found 0/15 target-visible decision frames and 0.0 m replay error.
**Geometry corrections.** Seed 1062 exposed two non-paper checks: a 1 m
standoff/0.5 m minimum hop that could exceed its own gate, and a verifier that
compared off-axis Euclidean slant range against camera-forward `d_f`. Both were
removed/corrected and locked with focused tests. The corrected seed still had
0/89 target-visible decision frames, false historical acquisition, 29 LOST
recoveries, and ended 85.82 m from goal.
**Result.** Seeds 1060 and 1062 are two final-profile failures, so 4/5 is
mathematically impossible. Seeds 1063-1064 and held-out seeds 1-40 are not
spent. Status: mechanism integrated; local Qwen3-VL 8B profile rejected. See
`reports/paper_implementation/ONFLY_QWEN_ROOT_CAUSE.md`.

### D-49 — Native-dynamics Qwen3-VL 4B closes OnFly's remaining adapter hypotheses
**When.** 2026-08-27 — paper-native dynamics, exact replay and installed-backend audit
**Decision.** Keep the corrected C3/C4/C5 OnFly mechanism in the shared
testbed, but reject the current Qwen3-VL 4B compatible backend. Do not repair
the gate by returning to an old position, adding goal truth/color rules, or
weakening the frozen SUPER substrate. Sequential acceptance work remains at
OnFly until a capable backend or released native implementation exists.
**Corrections before judgment.** The native profile now uses 0.6 m/s speed and
acceleration plus 0.4 rad/s yaw. Qwen receives the paper's chronological
multi-image memory rather than a lossy composite sheet. `CONTINUE`/`LOST`
separate recovery-anchor validity from current reacquisition; monitor evidence
and last-normal yaw are synchronized to the exact retained frame; and reaching
the recovery heading holds the viewpoint until monitor confirmation. The
previous-goal reprojection supplies a non-privileged temporal-continuity check.
Sixty-one focused contract/router tests and changed-file Ruff pass.
**Evidence.** C3 without the monitor entered the goal region on seed 1061,
proving the decision/verifier/planner path under native dynamics. Full C5 seed
1061 nevertheless timed out 15.778 m away with zero collisions. Exact replay
showed that the target remained occluded even in an offline counterfactual at
the true goal yaw, so the paper's yaw-only recovery could not reacquire it.
Seed 1060 timed out 25.413 m away with 0/89 target-visible frames; 63/89 plans
were correctly infeasible because the VLM repeatedly selected surfaces with no
known-free stopping prefix. Two failures make 4/5 impossible; seeds 1062-1064
were not spent on the new profile and held-out seeds 1-40 remain untouched.
**Backend audit.** Qwen3-VL 8B repeats the history/latest temporal error.
Qwen3-VL 2B, Qwen3.5 2B/4B, MiniCPM-V 4.6 and Gemma 3/4 fail fixed coordinate
or monitor gates. The exact downloaded Qwen3-VL-4B AWQ files load, but one
monitor response took 178.09 s and 10.56 GiB; Gemma 4 produced no positive
target verdict and ranged from 2.18 to 124.34 s. No remaining installed model
meets both capability and the 2 s cycle.
**Status.** mechanism integrated; compatible-backend gate rejected. Evidence:
`reports/paper_implementation/ONFLY_QWEN4_NATIVE_ROOT_CAUSE.md` and
`reports/paper_implementation/onfly_qwen4_native_gate.json`. Final verification:
61 focused tests and changed-file Ruff passed; the complete repository
regression passed 345 tests in 479.92 s. The architecture config validates with
the architecture-only `validate-config` command, while the environment is
validated by the typed loader in the passing native-profile test.
The official OnFly repository was checked again on 2026-08-30 and still stated
`Code coming soon`; no native implementation or checkpoint was available to
replace the rejected compatible backend.

### D-50 — PMR starts with learned-CVI, not the existing rule trigger
**When.** 2026-08-30 — primary-paper audit and first shared-runtime integration
**Decision.** Advance after OnFly's conclusive rejection and implement PMR as
C6 inside the shared testbed. The previous C6 rule gate is retained only as an
ablation/sentinel; it is not labeled PMR. Add admission as a configured plugin
so C6 does not receive a private runtime.
**Evidence.** PMR defines a fixed 18D compact runtime vector, a sigmoid-linear
learned-CVI score, threshold 0.997, budget/cooldown/terminal guards, a
no-progress-plus-blocked hard-stuck override, and a predefined recovery-skill
boundary. The paper discloses neither fitted weights nor normalization and has
no linked source release, so `pmr_cvi` requires an explicitly trained,
versioned checkpoint and fails closed without one.
**Implementation.** Added typed admission runtime/decision contracts, a plugin
registry slot, an observable admission event, shared trigger-loop routing, and
the 18D PMR feature/checkpoint implementation. The existing verifier, SUPER
planner, shield and controller remain the only execution path. Initial focused
verification: 107 tests pass and Ruff is clean; the complete repository
regression passes 349 tests in 455.17 s.
**Next.** Collect paired K=5 local/invocation utility labels on the locked
non-held-out split, fit and freeze the linear gate, then replace the scripted
bounded reasoner with a real typed recovery-skill reasoner. Fidelity and seed
lock: `docs/fidelity/PMR.md`.

### D-51 — Freeze the real PMR recovery boundary before training CVI
**When.** 2026-08-31 — recovery implementation and local-model capability gate
**Decision.** Do not train learned-CVI labels against the scripted
`bounded_reasoner`; that would learn when the sentinel is useful rather than
when PMR reasoning is useful. First freeze a real constrained recovery reasoner
and the multi-model inference composition, then collect paired labels.
**Implementation.** Added `pmr_recovery_reasoner`, which requests strict JSON
from `gpt-oss:20b`, permits only eight named semantic decisions and nine bounded
options, locally grounds them into typed skills, and uses the shared
verifier/SUPER/shield/controller route. Added `role_router` so the same C6
profile uses Qwen3-VL 4B for OnFly policy calls and GPT-OSS 20B for recovery
calls without a private model client. Added a PMR-matched shielded C3 comparator
and a C6 profile that fails closed until its trained checkpoint exists.
**Evidence.** Seven new offline tests cover schema rejection/retry, safe
fallback, simulated-backend refusal including nested routes, per-role model
identity, and shared verifier/planner routing. The real three-case probe first
revealed mode collapse to `safe_hold_verify`; after adding the missing semantic
definitions, both consecutive runs produced the same valid sequence:
blocked→`local_repair/ascend`, lost→`goal_alignment/scan_left`, and
stalled-visible→`goal_resume/approach_target`, with no fallback.
Changed-file Ruff passes; the complete repository regression passes 356/356
tests with zero failures or errors in 496.35 s.
**Next.** Implement deterministic paired K=5 utility collection from identical
pre-intervention states. Do not treat the static probe as mission-level PMR
success and do not consume held-out seeds 1-40.

### D-52 — C5 OnFly works after fixing context rejection and recovery re-entry
**When.** 2026-09-01 — exact-run visual debugging on seeds 1060/1061
**Decision.** Reopen the old compatible-backend rejection. Freeze the shared
Qwen context at 8192, make Ollama request errors fatal, emphasize the latest
monitor frame, and allow one bounded reorientation per continuous LOST episode.
Do not add target-specific search or simulator truth.
**Evidence.** Ollama explicitly reported 4430 prompt tokens against a 4096
context on the first four-image failure. Exact offline gates return LOST on the
four-image occlusion and STOP on the six-image near-goal case after correction.
Seed 1061 then succeeds at 0.652 m with a correct stop, one recovery, zero
collisions and zero parse errors. Offline replay scores monitor visibility at
0.95 and visually confirms occlusion, reacquisition and approach. Seed 1060
still has zero target-visible decision frames and fails after entering open
space; that is retained as a never-observed-target search limitation.
**Status.** C5 mechanism demonstrated; five-seed development gate remains open.
Full evidence is in
`reports/paper_implementation/ONFLY_QWEN4_RECOVERY_FIX_20260901.md`.

### D-53 — Qwen-VLA collection is a declared local-simulator-bound tool
**When.** 2026-09-01 — complete regression audit after D-52
**Decision.** Add `training/qwen_vla_dataset.py` to the pinned portability
exception set. Like the existing dataset, DAgger and replay-video tools, it
temporarily wraps `DeterministicEnv.step` so image/action labels share an exact
tick; it is not simulator-portable and must be replaced before AirSim data
collection.
**Evidence.** The complete regression reached 367 passes with this as its only
failure; source inspection confirmed the wrapper is restored in `finally` and
is used solely during collection.

### D-54 — C5 OnFly fails the retained five-seed capability gate
**When.** 2026-09-01 — systematic exact replay on development seeds 1060–1064
**Decision.** Freeze the corrected C5 mechanism and report the negative
five-seed result. Do not introduce target-specific scans, simulator-truth
steering, or a policy schema that regresses the demonstrated seed-1061 success.
**Evidence.** Seed 1061 succeeds at 0.519 m. Seeds 1060, 1062, and 1063 have
0 target-visible decision frames; seed 1064 has 9 early visible frames and then
loses tracking. Aggregate success is 1/5 with zero collisions, zero inference
errors, and zero policy/monitor parse errors. Exact replay separates
never-observed-target search from post-acquisition tracking failure.
**Status.** The runtime and monitor defects are fixed, but the shared
Qwen3-VL-4B C5 configuration fails the locked 4/5 capability gate. Full
evidence:
`reports/paper_implementation/C5_RETAINED_FIVE_SEED_RESULTS_20260901.md`.

### D-55 — “Choose the best viewpoint” prompting does not create coverage
**When.** 2026-09-02 — prompt-only C5 ablation on development seeds
**Decision.** Reject and revert a stronger prompt that retained the `u,v`
schema but requested a free-space observation viewpoint maximizing new visual
coverage whenever the target was absent.
**Evidence.** The seed-1061 positive control still succeeds at 1.496 m. Seeds
1060 and 1062 still have 0/89 target-visible decision frames; seed 1060 worsens
to 57.186 m and seed 1062 improves to 38.771 m without ever exposing the
target. Seed 1063 was interrupted after a backend stall at 88.15/90 simulated
seconds and is not counted.
**Conclusion.** A prompt can change direction but cannot infer which directions
were already covered from a current frame plus one history point. Preserve the
frozen C5 result and test explicit visited-view/frontier state as a separately
named extension. Evidence:
`reports/paper_implementation/C5_VIEWPOINT_PROMPT_EXPERIMENT_20260902.md`.

### D-56 — No released drone dataset ships our action space; relabelling from pose is the only path
**When.** 2026-09-04 — survey of public aerial VLA datasets, verified against the
HuggingFace API rather than search summaries.
**Decision.** Treat action relabelling as mandatory rather than optional, and
adopt a single normalisation contract — body-frame `[vx, vy, vz, yaw_rate]` in
m/s and rad/s, clipped to `constraints.max_speed_mps` — that every external
source must be converted into before any of it is mixed with our own data.
**Evidence.** Five repositories were checked by fetching their metadata and one
trajectory each, not by reading abstracts.

| Repository | Pixels | Action field | Units | Verified by |
| --- | --- | --- | --- | --- |
| `UPB-RAT-VLA/Exp2VLA-SingleCube-v1` | 480x640 video | 6-D `[vx,vy,vz,pitch,roll,yaw]` | normalised, not m/s | `meta/info.json`, `meta/stats.json` |
| `UPB-RAT-VLA/Exp2VLA-MultiObject-v1` | 480x640 video | same, 1500 eps / 370,500 frames | normalised | same |
| `AutelRobotics/CosFly` | RGB + depth + instance | **none** — `drone_pose` + `nav_waypoint` at 2 Hz | metres, CARLA world frame, degrees | `data_sample/.../trajectory.json` |
| `YunhengWang/WorldVLN_DataSet` | 333 tar shards | displacement + yaw change | metres | repo listing + paper |
| `yoofiannan/dronevla-dfr-episodes` | **none** | `[vx,vy,vz,yaw_rate,mission_state]` at 2 Hz | m/s — exact match | `episodes.jsonl`, `stats.json` |

The decisive finding is that Exp2VLA's nominal 6 degrees of freedom are not
real. Across both releases `vy`, `pitch` and `roll` are identically zero
(min = max = mean = std = 0), and `vx` has std 0.986 over the range [-1, 1] —
a bang-bang keyboard signal. It is a 3-channel dataset (forward, vertical, yaw)
with no lateral motion and no metric scale.

Conversely CosFly logs no action at all but logs pose at a fixed 0.5 s cadence,
from which our action space is an exact finite difference. Frames 0 to 1 of
`trajectory_1777083733` give `[-3.123, -2.072, -1.600]` m/s and a yaw change of
-3.13 deg over 0.5 s. That is our label, recovered arithmetically.
**Rejected.** Concatenating Exp2VLA with our data as-is. Its `+-1` commands and
our m/s commands would occupy the same output channels with different meanings,
so the model would be taught that the same number denotes two different speeds —
more data making the policy strictly worse. Also rejected: `dronevla-dfr`, which
has the exact action space we want but ships no images, and so cannot train a
model whose input is pixels.
**Status.** Survey complete; conversion not yet written. The engineering cost is
small and the semantic cost is where the risk sits — see the normalisation
contract above.

### D-57 — The drone-VLA field trains on discrete navigation actions, not velocity
**When.** 2026-09-04 — survey of ~45 aerial VLA/VLN systems, cross-checked
against two 2026 reviews and the HuggingFace API.
**Decision.** Stop treating "find a drone VLA dataset" as a search problem. The
field's dominant supervision signal is a discrete high-level move set, so the
velocity-controlled subset is small enough to enumerate exhaustively, and within
it only one release is both real-world and convertible to our action space.
**Evidence.** Grouping the field by what the action actually *is*:

*Discrete 4-DoF move sets* (forward / left / right / up / down / stop) — this is
the majority and holds nearly all the scale: AerialVLN and AerialVLN-S (8.4k
trajectories), OpenFly (100k), AirNav (143k real urban), UAV-ON, IndoorUAV
(5k), LANI (6k), plus the models trained on them — NavAgent, FlightGPT, STMR,
GeoNav, LogisticsVLN, SA-GCS, OpenVLN, SkyVLN, VLFly, AirStar, CityNavAgent,
FSD-VLN, LongFly, UAV-CodeAgents, MMCNav.

*Waypoint or path prediction*: CityNav (32k), AVDN (3k dialogs), UAV-VLA (30
satellite images), CosFly-Track, ImagineUAV, AeroDuo (13k pairs).

*Continuous low-level control* — the only group relevant to us:

| System | Data | Real? | Action | Released |
| --- | --- | --- | --- | --- |
| UAV-Flow Colosseo | 30k trajectories, pose at 5 Hz | **yes** | pose + unified instruction | `wangxiangyu0814/UAV-Flow` |
| OpenUAV | 12k trajectories | no | continuous 6-DoF | partial |
| CognitiveDrone | 1,766 eps / 104,483 frames, 10 Hz, 2 cameras | no | 7-D | `kingJulio/cognitive_drone_lerobot` |
| Exp2VLA | 494k frames | no | nominally 6-D, really 3 | yes — see [D-56](#d-56) |
| GRaD-Nav++ | **none** — differentiable RL in 3DGS | sim-trained, real-deployed | thrust/rate | no dataset |
| AutoFly | not published | no | `vx,vy,vz,omega_yaw` | no |

**Conclusion.** Two findings matter. First, UAV-Flow is the strongest external
candidate by a wide margin: it is the only *real-world* language-conditioned
continuous-control release, its logs are pose at a clean 0.2 s cadence, and one
sampled trajectory differentiates to sane body-frame velocities — vx -0.51,
vy 0.92, vz 0.00 m/s, all under 2 m/s — so our 4-D action space is recoverable
arithmetically. It also ships `preprocessed_logs` as start-relative 6-D pose and
an `instruction_unified` field, both of which reduce the conversion further.
Second, the strongest continuous result in the field (GRaD-Nav++, 67% real-world
on trained tasks) used **no demonstration dataset at all**; it trained by
differentiable RL in a photorealistic 3D Gaussian Splatting simulator. That is a
standing alternative to dataset assembly and should be recorded as such rather
than discovered late.
**Rejected.** Training on the discrete VLN corpora. They are where the scale is,
but a policy supervised on "move forward one step" cannot emit a velocity, and
converting a discrete move set into a velocity requires inventing the magnitude
we would be trying to learn.
**Status.** Survey complete. Conversion target selected (UAV-Flow); DiffRL
recorded as the unexplored alternative.

### D-58 — Correction: `[vx, vy, vz, yaw_rate]` *is* the convention; the dead channels are padding
**When.** 2026-09-04 — user challenged the breadth of the D-57 survey.
**Decision.** Withdraw the D-56/D-57 claim that our action space is unusual and
that no dataset shares it. The opposite is true, and two earlier conclusions
built on that claim are void.
**Evidence.** CognitiveDrone states it "generates real-time **4D** action
commands" and that the drone "is controlled using **velocity setpoints**,
ensuring consistency with real-world drones running **ArduPilot** firmware"
(arXiv 2503.01378). That is `[vx, vy, vz, yaw_rate]` exactly. It is not a
per-paper choice at all — it is the MAVLink/ArduPilot/PX4 velocity setpoint
interface, which is why `yoofiannan/dronevla-dfr` and AutoFly independently
report the same four fields, and why our own `_base.yaml` uses it.
**The padding finding.** The stored vectors that appear wider than 4-D are
manipulator-shaped containers, not richer actions. CognitiveDrone is fine-tuned
from OpenVLA-7B, whose action head is a 7-D arm vector
`(x, y, z, roll, pitch, yaw, gripper)`; the LeRobot mirror duly stores
`actions float32 [7]`. Exp2VLA stores `[vx, vy, vz, pitch, roll, yaw]` with
`vy`, `pitch` and `roll` identically zero. Both are four real degrees of freedom
occupying a slot sized for an arm. D-56 read Exp2VLA's zero channels as a
defective dataset; they are padding, and the reading was wrong.
**What this changes.** The barrier to pooling is *units and per-airframe speed
limits*, which is a scalar per dataset, not *incompatible action semantics*,
which would have been a modelling problem. Normalisation is still the right
representation, but as a convenience rather than a rescue. The CHANGES.md claim
that "we are the odd one out for storing m/s" is withdrawn: we store what
ArduPilot accepts.
**Status.** D-56 and D-57 stand only on their per-repository measurements. Their
conclusions about convention are superseded here.

### D-59 — Survey redone from primary sources; no single action convention exists
**When.** 2026-09-04 — 25 systems read from their own action and training-data
sections after the D-57 review-derived survey was challenged as too narrow.
**Decision.** Replace the D-57 grouping with a four-way taxonomy taken from
primary sources: velocity, relative displacement, waypoint/pose, and discrete
primitives. Full table: `docs/research/DRONE_VLA_SURVEY_20260904.md`.
**Evidence.** RaceVLA (2503.02572) states it replaced OpenVLA's 7-D manipulator
vector with a 4-D drone signal of three linear velocities plus yaw rate;
CognitiveDrone (2503.01378) ties the same four fields to ArduPilot velocity
setpoints. UAV-Flow (2505.15725) is 30,692 **real** trajectories on a DJI Mavic
3T RTK at 5 Hz with centimetre accuracy, storing 6-DoF pose. OpenFly (100 k) and
IndoorUAV (51 k) are the largest corpora and both emit discrete primitives.
**Corrections this forces.** D-57's claim that the field has a single consensus
was wrong in both directions: there is no field-wide convention, but there *is*
a firm one within velocity-output models, and ours matches it. D-56's reading of
Exp2VLA as a defective dataset and D-58's reading of it as mere padding are both
superseded — its paper defines a genuinely 3-D action, deliberately omitting
lateral velocity.
**Two findings not previously recorded.** VLFly and See, Point, Fly reach
real-world performance **training-free**, grounding a waypoint in the image with
a pre-trained VLM — architecturally close to C5 OnFly and viable within 8.6 GB.
And Think Like a Pilot and SpatialFly are both ~3 B with LoRA and frozen
encoders, making them the hardware-matched precedents for anything we train.
**Status.** Survey complete from primary sources. Supersedes D-57.

### D-60 — C5 cannot fly past what it can see; the cause is structural, not prompting
**When.** 2026-09-04 — comparison of C5 OnFly against See, Point, Fly (2509.22653)
and VLFly (2506.10756) after the primary-source survey.
**Decision.** Stop attributing C5's search failure to the prompt. Test SPF's
VLM-predicted travel distance as a single-variable ablation of C5.
**Evidence.** SPF is C5's architecture — VLM names a pixel, pinhole unprojection
gives a body-frame displacement, closed loop — reached independently and
validated on real hardware. The sole structural difference is who sets the step
length. SPF asks the VLM for `(u, v, d_VLM)` and maps it through
`d_adj = max(d_min, s*(d_VLM/L)^p)` with no depth sensor. C5 asks only for
`(u, v)` and takes the distance from the depth image at `onfly.py:509`, so
`range <= sensed_depth(u, v)`. The hop is therefore bounded by the first surface
along the chosen ray: C5 is structurally incapable of travelling past what it
can already see. `bearing_gated_range` compounds this by multiplying the range
by a Gaussian in image bearing, shortening exactly the off-axis moves that
exploration requires.
**What this retires.** D-55 concluded that a viewpoint-selection prompt "cannot
create coverage". The mechanism is now identified: the prompt changed which
pixel was chosen but could not lift the depth cap on the resulting hop. The
observation stands; the explanation was incomplete.
**Constraint check.** SPF uses no depth sensor, so adopting `d_VLM` *removes* a
privileged input. This makes the substrate weaker, not stronger, and so does not
hide the search boundary.
**Status.** Ablation specified, not yet run. Detail:
`docs/research/C5_VS_TRAINING_FREE_VLA_20260904.md`.

### D-61 — Model-named step implemented and unit-tested; evaluation deferred on GPU contention
**When.** 2026-09-04 — implementation of the D-60 ablation.
**Decision.** Ship the SPF step as an opt-in policy parameter rather than a
change to C5, and defer the five-seed evaluation rather than run it against a
busy GPU.
**What was built.** `OnFlyDecisionAgent` gained `step_from_model` (default
**False**, so every frozen C5 number stays reproducible). When enabled, the
decision schema carries a third field `d` in `1..step_levels`, and the step
becomes SPF's `d_adj = max(d_min, s * (d/L)^p)` in place of the depth-derived
`gated` range. The sensed depth and the bearing gate are still computed and
recorded, so `sampled_depth_m`, `gated_range_m`, `executable_range_m`,
`step_source` and `model_step_level` sit side by side in provenance and the two
step sources can be compared on the same run. Config:
`configs/architectures/c5_onfly_qwen4_spf_step_dev.yaml`. Runner:
`scripts/run_c5_spf_step_seeds.sh`.
**One design correction made before running.** `step_scale_m` was first set to
9.0, which would have confounded *who decides the step* with *how far a step may
be*, and would have been rejected by the inherited verifier at image edges where
the 3-D ray exceeds `max_waypoint_distance_m`. It is now 7.0, exactly C5's own
`max_depth_m`, so the maximum reach is unchanged and only the source of the
distance differs. The level ladder is 1.4, 2.8, 4.2, 5.6, 7.0 m.
**Tests.** Five new cases in `tests/unit/test_onfly.py` cover the step curve and
its floor, schema presence and absence, the fact that the same pixel yields two
different ranges purely from `d`, that `step_source` still reports `depth` by
default, and that a missing `d` fails closed.
**Why the evaluation did not run.** `nvidia-smi` showed the 8.2 GB card at 99%
utilisation with 7.8 GB held by UE4Editor, `valley_operator_experiment.py` and a
loaded llama-server — a separate active experiment. Starting a second Qwen3-VL
4B profile would have competed for the remaining ~370 MB and risked killing that
run. No result is worth that, and a result measured under contention would not
be trustworthy anyway.
**Status.** Implementation complete and tested. Evaluation pending a free GPU.

### D-62 — Correction: the step length is not C5's binding constraint; direction is
**When.** 2026-09-04 — measurement on the frozen baseline runs, before spending
GPU time on the D-60 ablation.
**Decision.** Withdraw D-60's hypothesis and do **not** run the model-named-step
ablation as specified. The code claim was right; the causal claim was wrong.
**Evidence.** Measured over the four retained seed-1060/61/63/64 baseline runs:

| seed | decisions | sensed depth under the 7 m cap | mean commanded range | bearing-gate loss |
| ---: | ---: | ---: | ---: | ---: |
| 1060 | 89 | 35% | 5.31 m | 10% |
| 1061 | 85 | 35% | 5.09 m | 13% |
| 1063 | 89 | 15% | 6.21 m | 5% |
| 1064 | 89 | 17% | 5.45 m | 18% |

Two facts follow, and both contradict D-60. First, the depth ceiling binds only
35% of the time on seed 1060 — most steps are limited by the configured
`max_depth_m = 7.0`, not by an obstacle. Second, and decisively, the vehicle
travels a mean of **0.517 m** between consecutive decisions against a mean
commanded range of **5.315 m**: it realises **9.7%** of the step before the
waypoint is replaced. The decision interval is 1.000 s (median; mean executed
decision age 1.049 s), so at the native-dynamics 0.6 m/s the vehicle can cover
at most 0.600 m per decision — exactly the measured maximum. A 7 m step would
need roughly 12 s of committed flight and never gets it. The verifier accepted
89 of 89 proposals, so it is not the limiter either.
**Therefore.** The waypoint's *distance* is very nearly irrelevant to C5's
trajectory; only its *direction* survives replanning. Swapping the source of the
distance — depth-derived or model-named — changes at most a tenth of a metre per
decision. Running it would have produced a null result that looked like a
refutation of SPF, which it would not have been.
**What this means for the SPF comparison.** The transferable difference is not
the `d` field. It is that SPF *executes* the step it names before re-observing,
whereas C5 replans over it at ~1 Hz. The meaningful experiment is commitment —
hold a waypoint until it is reached or invalidated — and that touches the
asynchronous schedule, which is a declared paper variable rather than a plugin
parameter. It must be specified as such before it is run.
**Status of the implementation.** The `step_from_model` code and its five tests
are correct and are kept, defaulted off, as the mechanism the commitment
experiment will need. D-60's mechanism claim is superseded; D-55's original
observation — that direction changes do not create coverage — stands and is now
better supported than when it was written.

### D-63 — Two tests are load-sensitive, not broken
**When.** 2026-09-04 — while validating the D-61 implementation.
**Decision.** Record `tests/integration/test_verify.py::[c1]` and
`tests/smoke/test_all_architectures.py::test_the_core_runtime_imports_no_heavy_dependency`
as machine-load sensitive, so a future red run is not misread as a regression.
**Evidence.** Both failed in a full-suite run taken while three pytest processes,
UE4Editor, a `valley_operator_experiment.py` and a loaded llama-server were
competing for the machine. Both pass in isolation, on the baseline tree (2
passed in 230.6 s) and with the OnFly changes applied (2 passed in 105.2 s).
The smoke failure is impossible to attribute to the OnFly change in any case:
`uavlab.plugins.reasoning.onfly` is not imported by `import uavlab` or by
`uavlab.core.orchestrator`, and a direct probe reports no forbidden module
loaded. C1's verify test drives real `gpt-oss:20b` inference through Ollama and
so is sensitive to GPU contention by construction.
**Status.** No code change. Run the full suite on an otherwise idle machine
before treating either as a real failure.

### D-64 — The retained C5 benchmark is not a search task; it is a 35 m corridor with almost no slack
**When.** 2026-09-04 — direct measurement of `grid_nav_onfly_native_dynamics` at
reset, prompted by D-62 showing that step length cannot explain the failures.
**Decision.** Stop describing the retained five-seed failure as a search or
viewpoint-selection problem. It is an obstacle-detour problem under a path
budget, and the exploration framing in D-55, D-60 and the coverage-prompt work
was aimed at a problem this benchmark does not pose.
**Evidence.** Measured by resetting the environment on each seed:

| seed | start distance | goal bearing | occluders on the direct ray | outcome |
| ---: | ---: | ---: | --- | --- |
| 1060 | 35.0 m | +0.0 deg | 2, at 12.4 m and 15.6 m | never seen |
| 1061 | 35.0 m | +0.0 deg | 1, at 15.0 m | **success** |
| 1062 | 35.0 m | +0.0 deg | 3, at 11.7, 15.1, 24.1 m | never seen |
| 1063 | 35.1 m | +0.0 deg | 2, at 16.4 m and 21.1 m | never seen |
| 1064 | 35.0 m | +0.0 deg | none | seen 0-8 s, then lost |

The target sits **dead ahead at 35 m on every seed**; the seed varies the
obstacle layout, not the target bearing. There is nothing to search for and no
viewpoint to choose — the correct opening action is to fly straight.

The budget is the binding constraint. At the native-dynamics 0.6 m/s over a 90 s
horizon the entire path budget is 54 m, of which 35 m is the straight-line
distance, leaving **19 m of slack** for every detour, overshoot and heading
correction combined. Measured path lengths were 45.1-46.3 m, i.e. 84-86% of the
budget: the vehicle is speed-saturated for essentially the whole episode.
**Reading.** Across these five seeds the outcome tracks the number of occluders
on the straight-line ray monotonically — one occluder succeeds, two or three
never acquire, and the zero-occluder seed is the only one that sees the target
at all. Each detour spends slack the mission does not have. With n=5 this is a
consistent pattern rather than a demonstrated law, but the structural facts it
rests on (fixed 35 m, fixed bearing, 54 m budget) are exact.
**What this retires.** The "go where you cannot yet see" boundary, as posed
against *this* benchmark, is not the live question; D-55's viewpoint prompt and
D-60's step-source hypothesis were both answering a question the seeds do not
ask. It also explains why the coverage prompt's most effective component was the
instruction to preserve the initial heading: on this benchmark the initial
heading is the answer.
**Consequence.** Either the benchmark should be changed so that search is
actually required — vary the target bearing, or raise the horizon so detours are
affordable — or C5 should be judged on obstacle detour efficiency, which is what
it is really being asked to do. That is a benchmark-design decision and is left
for the user.
**Status.** Measured, recorded, no code change.

### D-65 — C5's real failure is a geofence deadlock, not search, detour cost, or budget
**When.** 2026-09-04 — 240 s horizon run (`grid_nav_onfly_native_long`) against
the classical `c0` baseline on the same seeds.
**Decision.** Name the retained-seed failure precisely: the vehicle reaches the
geofence boundary and then deadlocks, because every waypoint it proposes lands
outside the fence and is rejected, and nothing turns it around.
**Evidence.** Seeds 1060 and 1062 both end frozen — identical position, zero
speed — for the last 97 s and 108 s of a 240 s episode:

| seed | freeze at | held | distance from home | verifier during freeze |
| ---: | ---: | ---: | ---: | --- |
| 1060 | 143 s | 97 s | 55.25 m | 0 accepted, 96 rejected |
| 1062 | 132 s | 108 s | 56.05 m | 0 accepted, 107 rejected |

The first rejection reason is explicit: *"target is 62.1 m from home, outside the
60 m geofence"*. At 55 m from home with a 7 m maximum reach, every outward
proposal lands at ~62 m and is correctly refused. The policy keeps proposing
outward, the verifier keeps refusing, and there is no fallback, so the vehicle
holds position until the horizon expires.
**Why this is the intersection of two known defects.** The decision agent's
measured centre bias — chosen `u` median 116 against an image centre of 112,
59% of commands within 10 degrees of straight ahead — means "ahead" is what it
almost always proposes. Ahead, at the fence, is always inadmissible. A policy
that could steer would escape; a fence-aware fallback would also escape; C5 has
neither, so the two defects compose into a hard deadlock.
**What this retires.** More time does not help and the earlier budget reading is
not the operative cause. Seeds 1060 and 1062 used only 78 m and ~80 m of a 144 m
budget. D-64's measurement of the corridor stands, but the 90 s horizon merely
hid this deadlock behind an earlier timeout.
**Positive result.** Where acquisition succeeds the architecture is competent:
seed 1061 reached the target in 85 s against `c0`'s 67 s on the same seed, at
1.27x the time of a classical planner that already knows the goal position, with
6% stationary ticks against 43-46% in the deadlocked seeds.
**Confirmation on seed 1063.** The same deadlock, and the discriminator is
clean. Every failing seed freezes at 55.3-56.1 m from home with 100% of the
verifier calls during the freeze refused for the geofence:

| seed | freeze | held | from home | rejections during freeze | geofence refusals over the whole run |
| ---: | ---: | ---: | ---: | --- | --- |
| 1060 | 143 s | 97 s | 55.3 m | 96/96, all geofence | 99/239 |
| 1062 | 132 s | 108 s | 56.1 m | 107/107, all geofence | 110/239 |
| 1063 | 109 s | 131 s | 55.5 m | 131/131, all geofence | 133/239 |
| **1061** | — | 0 s | 34.8 m | — | **0/85** |

The successful seed has **zero** geofence refusals across the entire episode;
the three failures spend 41-56% of all verifier calls being refused for it. On
these seeds the presence of geofence refusal separates success from failure
perfectly.
**Complete five-seed result.** 1/5 at 240 s, identical to 1/5 at 90 s. The extra
150 seconds changed no outcome. Every one of the four failures ends frozen
55.3-56.1 m from home:

| seed | occluders on ray | c0 | C5 | freeze | held | from home | geofence refusals |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 1060 | 2 | 68 s | timeout | 143 s | 97 s | 55.3 m | 99/239 |
| 1061 | 1 | 67 s | **success, 85 s** | — | — | 34.8 m | **0/85** |
| 1062 | 3 | 63 s | timeout | 132 s | 108 s | 56.1 m | 110/239 |
| 1063 | 2 | 83 s | timeout | 109 s | 131 s | 55.5 m | 133/239 |
| 1064 | **0** | 84 s | timeout | 151 s | 89 s | 55.7 m | 91/239 |

**This supersedes D-64's occluder reading.** Seed 1064 has a completely clear
line of sight to the target and still fails, by the same deadlock at the same
radius. Occluder count does not explain the outcomes; geofence refusal does,
and it separates the five seeds perfectly. D-64's measurements of the corridor
geometry stand — the target really is dead ahead at 35 m on every seed — but the
causal reading built on occluder counts was wrong, and was drawn from four
seeds when the fifth contradicted it.
**Status.** Complete. No fix attempted — the fallback is a real architecture
decision, not a patch.

### D-66 — Told the winning route in words, C5 does worse: 0/5 against 1/5
**When.** 2026-09-04 — privileged capability probe, 240 s horizon, seeds 1060-1064.
**Status of the evidence.** PRIVILEGED. The route handed to the model is derived
from `c0`'s successful trajectory on each seed, i.e. simulator truth injected
into the prompt. These numbers answer "can the decision agent execute a route it
is told?" and must never be quoted as C5 performance. Configs carry
`privileged_diagnostic` in their tags and a warning header.
**Setup.** `c0`'s path per seed was simplified (Douglas-Peucker, 1.5 m) to 2-5
straight legs and rendered as text — e.g. seed 1060: *"after 0 m of path, turn
left 47 degrees and fly 12.6 m; after 13 m, turn right 31 degrees and fly 3.8 m;
after 16 m, turn right 40 degrees and fly 23.2 m."* — and injected into the
decision prompt alongside live onboard odometry (path flown, straight-line
distance from home, heading change from initial) so the agent could locate
itself on the route. Nothing else changed; the agent still emits its own pixel.

| seed | no hint | with route | geofence refusals | median `u` | stationary |
| ---: | --- | --- | --- | ---: | ---: |
| 1060 | timeout 24.6 m | timeout 24.8 m | 99 -> 101 | 112 | 46% |
| 1061 | **success 0.5 m** | **timeout 24.7 m** | 0 -> **128** | 101 -> 112 | 54% |
| 1062 | timeout 24.5 m | timeout 24.5 m | 110 -> 94 | 112 | 39% |
| 1063 | timeout 19.5 m | timeout **15.0 m** | 133 -> **0** | 116 | **3%** |
| 1064 | timeout 25.8 m | timeout 22.8 m | 91 -> 95 | 112 | 40% |

**Result. 0/5 with the route against 1/5 without.** Being told exactly where to
fly made the architecture strictly worse.
**The route is not ignored, but it is not followed either.** An early reading of
seeds 1060 and 1061 alone suggested the hint was inert; seed 1063 refutes that.
There the hint eliminated the geofence deadlock outright (133 refusals to zero),
cut stationary time from 60% to 3%, and produced the closest approach recorded
on that seed. On seed 1061 it did the opposite, converting the only success into
a 128-refusal deadlock. The mechanism is live and its sign is seed-dependent.
**Median `u` is 112 on four of five seeds, and the image centre is 112.** On the
one seed where the agent had been steering without the hint (1061, median 101)
the added text moved it to exactly centre. The centre bias therefore behaves
like a fallback under prompt load rather than a fixed habit, which predicts that
further prompt engineering degrades steering rather than improving it.
**Consequence.** Under the pixel contract this model cannot be talked into a
route. The remaining question is whether the failure is the model or the output
representation, which the discrete-direction contract isolates. Acceptance there
is bearing spread beyond +-10 degrees, not mission success.

### D-67 — The steering failure is the model, not the output representation
**When.** 2026-09-04 — privileged capability probe, route hint plus the
five-word steering contract, 240 s horizon, seeds 1060-1064.
**Status of the evidence.** PRIVILEGED, as D-66. The route is `c0`'s successful
trajectory rendered as text. Not reportable as C5 performance.
**Decision.** Close the output-contract hypothesis. Two independent output
representations produce the same degenerate behaviour, so the pixel encoding was
never the cause.
**Result.** 0/5, the same as the pixel contract with the route (D-66) and worse
than the 1/5 with no hint at all.

| seed | end | t | final | n | modal word | entropy | distribution |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1060 | agent_stopped | 23 s | 32.87 m | 23 | 65% | 0.40 | left 15, right 8 |
| 1061 | agent_stopped | 185 s | 8.50 m | 185 | 89% | 0.23 | right 165, ahead 18, left 2 |
| 1062 | timeout | 240 s | 30.15 m | 239 | 99% | 0.04 | left 236, right 3 |
| 1063 | timeout | 240 s | 39.02 m | 239 | 99% | 0.03 | right 237, left 2 |
| 1064 | timeout | 240 s | 56.11 m | 239 | 79% | 0.32 | right 189, left 50 |

Entropy is normalised over the five-word vocabulary: 1.0 uses it, 0.0 is one
word forever. The observed range is 0.03-0.40.
**The acceptance criterion inherited from `c5_onfly_qwen4_direction_dev` is
wrong.** It asked whether commanded bearings spread beyond +-10 degrees, which
seeds 1061-1064 pass while emitting a single word 79-99% of the time. The test
detects *not-centre*; it does not detect *not-constant*. Any future contract
experiment must use a distributional measure. Recorded so the earlier criterion
is not reused.
**Two structural limits found alongside it.** Across all 925 decisions the model
chose `hard_left` **zero** times and `hard_right` **zero** times, so the
effective vocabulary is the inner three words and it then collapses onto one of
them. Separately the vocabulary is under-ranged for the task: the five routes
require turns of 12-72 degrees and 9 of 16 exceed the +-38 degree maximum a
single command can express, because the bearings are bounded by the camera
half-angle.
**False stops persist and are unrelated to steering.** Seeds 1060 and 1061 ended
`agent_stopped` — the monitor declaring arrival — at 32.87 m and 8.50 m from a
2 m goal radius, with `latest_scale=large` and `acquisition_count=2/2` on 1060
while the vehicle had moved barely 2 m. This is the acquisition latch, a defect
independent of the decision agent.
**Conclusion.** Qwen3-VL 4B does not steer from vision in this task under either
representation. Combined with D-66, the capability boundary is now located in
the model rather than in the prompt, the coordinate contract, the step source or
the path budget, each of which has been separately excluded.

### D-68 — Gemma steers and Qwen does not, and it changes nothing
**Model-comparison claim superseded by D-71: all five runs actually called Qwen.**
**When.** 2026-09-04 — `c5_onfly_gemma4b_direction_dev`, unprivileged (no route
hint), 240 s horizon, seeds 1060-1064. Acts on the standing instruction to try
Gemma 4B if the discrete-direction contract failed, which D-67 established.
**Decision.** Separate the steering question from the failure question. They are
not the same question, and the answers point in opposite directions.
**Steering: the user's claim is confirmed, with no overlap between the models.**
Normalised entropy over the five-word vocabulary, per seed:

| model | 1060 | 1061 | 1062 | 1063 | 1064 | mean | modal word |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Qwen3-VL 4B | 0.40 | 0.23 | 0.04 | 0.03 | 0.32 | **0.21** | 65-99% |
| Gemma 3 4B | 0.68 | 0.68 | 0.53 | 0.52 | 0.58 | **0.60** | 36-66% |

Every Gemma seed exceeds every Qwen seed. Gemma spreads across the vocabulary;
Qwen emits one word 79-99% of the time on its full-length runs. Gemma also
reached `hard_right`, which Qwen never selected in 925 decisions.
**Outcome: 0/5, worse than the 1/5 Qwen pixel baseline.**

| seed | end | final | closest | stationary | geofence refusals |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1060 | timeout | 67.02 m | 23.63 m | 27% | 64/239 |
| 1061 | agent_stopped | 14.19 m | 14.19 m | 3% | 0/39 |
| 1062 | timeout | 61.67 m | 22.71 m | 54% | 130/239 |
| 1063 | timeout | 31.07 m | 16.04 m | 59% | 136/239 |
| 1064 | timeout | 63.25 m | 26.96 m | 41% | 99/239 |

Closest approaches of 16-27 m are indistinguishable from Qwen's 19-26 m. Three
times the steering entropy bought no additional progress toward the target.
**Conclusion. Steering was never the binding constraint on this benchmark.** The
geofence deadlock of D-65 reappears unchanged under the model that steers well —
64 to 136 refusals on four of five seeds — and seed 1061 adds a fourth false
stop, at 14.19 m from a 2 m goal radius, with the same
`latest_scale=large, acquisition_count=2/2` signature seen twice under Qwen.
**Consequence for the fix order.** Two defects are now demonstrated to be
model-independent and are the live blockers: the absence of any fallback when
every proposal is refused for the geofence, and the acquisition latch that
declares arrival at 8.5-32.9 m. The Qwen steering deficiency is real and
measured, but fixing it alone would not have changed a single outcome here.


### D-69 — Target-bound arrival and bounded fence recovery experiments
**When.** 2026-09-07 — user approved separate arrival and boundary fixes.
**Status.** Provisional; development-only profiles, baseline unchanged.
**Decision.** First bind STOP to a monitor-authored target pixel in the current
synchronized RGB-D observation, with finite uncapped range, distinct-frame
confirmations and world-point consistency. A navigation waypoint's depth is
not evidence of target range. Keep distant acquisition distinct from arrival.
Then independently add bounded inward reorientation after repeated geofence
rejections, using only odometry and the declared fence. Neither experiment may
read goal truth, introduce a detector, or replace VLM waypoint decisions.
**Evidence.** Existing STOP reads sampled_depth_m from last_decision: a policy
navigation pixel, not a monitor-grounded target. D-65's deadlocks begin after
109–151 s and cannot explain all 90 s failures. Steering entropy alone does not
establish steering accuracy.
**Validation.** Contract regressions first, then separate development profiles
on seeds 1060–1064 (1061 positive control), plus the long profile for boundary
recovery. Seeds 1–40 remain untouched. Mission success must be measured;
fewer stops or refusals alone do not establish improvement.

**Implementation validation (D-69).** Three separate development profiles are
implemented. 281 unit/contract tests and 31 shared-runtime integration tests
pass (312 total); the real-inference all-architecture termination test was
excluded. Real-model development flights remain pending GPU availability;
UE4Editor was left running. No new capability result is claimed. Details:
`reports/paper_implementation/C5_ARRIVAL_FENCE_FIXES_20260907.md`.


### D-70 — New target-evidence schema exceeded the inherited output budget
**When.** 2026-09-07 — first real-model D-69 arrival flight.
**Evidence.** Exact monitor request on development seed 1061: at 48 tokens,
Ollama reports done_reason=length and the JSON is incomplete; at a 96-token
cap, the response finishes in 53 tokens with done_reason=stop and zero parse
errors. Artifact: `reports/paper_implementation/C5_TARGET_STOP_SCHEMA_PROBE_20260907.json`.
**Decision.** Raise num_predict to 96 only in the target-bound development
profile (inherited by its combined variant). Keep baseline and fence-only
profiles unchanged. This is an output-capacity correction, not a channel or
model swap. Retain the fixed simulated latency profile and report measured
latency separately; this is not evidence of real-time feasibility.
**Invalid run.** `runs/c5_target_stop_20260907_s1061` was interrupted after
repeated truncation failures and is not a capability result. Rerun under a new
output directory with the corrected manifest.


### D-71 — Historical Gemma comparison used the Qwen backend
**When.** 2026-09-07 — user requested comparison with drone_control's Gemma 4 E2B.
**Evidence.** All five `runs/c5_gemma_dir_s1060` through `s1064` manifests set
policy.model_id=gemma3:4b but inference.params.model_id=qwen3-vl:4b. Every
policy and monitor inference_call event identifies qwen3-vl:4b. The backend
uses its own configured model, not InferenceRequest.model_id. The current
c5_onfly_gemma4b_direction_dev config overrides only policy and monitor.
**Correction.** D-68 does not compare models. Its steering-entropy difference
cannot be attributed to Gemma, and its model-independent-defect claim is not
established by these runs. These five artifacts remain preserved as incorrectly
labelled Qwen experiments; their numerical observations are not Gemma results.
**Decision.** Prioritize a true Gemma 4 E2B comparison after the user's steering.
Pause the queued Qwen sweep, retaining completed runs and letting the current
flight finish. Explicitly set policy, monitor, and inference backend model IDs,
use Gemma's content channel with think=false, and verify raw image/JSON requests
before flights. Installed manifest digest is
7fbdbf8f5e45a75bb122155ed546e765b4d9c53a1285f62fd9f506baa1c5a47e.
Smaller observed GPU residency is not proof of better navigation; the same
development seeds and model/parse/latency logs determine capability.

**D-71 guard.** Ollama now rejects a request whose model_id differs from its
configured backend before any HTTP call. This prevents the historical silently
mislabelled experiment from recurring; previously misconfigured profiles now
fail explicitly instead of producing misleading results. The Gemma image
probe passed waypoint and both monitor JSON schemas with zero parse errors:
`reports/paper_implementation/GEMMA4_E2B_CONTRACT_PROBE_20260907.json`.


### D-72 — True Gemma 4 E2B is lighter and faster, but fails this navigation gate
**When.** 2026-09-07 — completed model-identity-verified development screen.
**Result.** Gemma 4 E2B scores 0/5, all timeouts; zero collisions, false stops
and monitor parse errors. Mean measured policy call 0.353 s, monitor
0.725 s. At 8192-token context GPU residency is 1.71 GB, versus Qwen's
4.24 GB. The retained Qwen baseline was 1/5; the new Qwen target-bound arrival
variant is 0/5. This does not establish superiority of either model generally.
**Interpretation.** Gemma's resource advantage is observed; navigation improvement
is not. The normalized simulated latency remains fixed, so potential benefit
from a faster native Gemma schedule is not evaluated here. No model is promoted.
**Validation.** 285 unit/contract tests pass after the identity guard. Qwen
boundary-only 90 s evaluation is partial (1/3, zero recovery triggers);
boundary-long and combined gates remain paused, not passed. No held-out model
evaluation was run. Evidence:
`reports/paper_implementation/GEMMA4_E2B_COMPARISON_20260907.md`.


### D-73 — Keep Gemma fixed for active OnFly development
**When.** 2026-09-07 — explicit user selection after D-72.
**Decision.** Use gemma4:e2b for both policy and monitor through the active
c5_onfly_active_dev profile, inheriting the identity-verified Gemma baseline.
This supersedes D-72's operational model-selection status, not its failed
capability gate. Historical configurations and results remain unchanged.
**Rationale.** User wants one resident model shared with the valley experiment
and wants navigation work focused on architecture and control flow. Do not
load another model or unload Gemma as routine preparation for these experiments.
Parallel valley use is authorized; record contention and do not treat shared
server wall-clock latency as an isolated model benchmark. Fixed simulated
latencies remain unchanged.
**Evidence.** D-72 establishes lower measured residency and five navigation
timeouts. This supports holding the model fixed during debugging; it does not
prove model quality irrelevant. Navigation is still unaccepted.
**Next diagnostic.** Trace existing Gemma runs from image and proposed waypoint
through verification, replanning, monitor intervention and realized motion.
Identify a concrete control-flow failure before another development sweep;
use simulator truth only for offline diagnostics.


### D-74 — Isolate previous-waypoint echo in Gemma policy
**When.** 2026-09-07 — architecture-flow investigation.
**Evidence.** Exact replay of all five D-72 flights has zero final-distance
error. 405/418 decisions with a history point reproduce it within one image
pixel. Only one of 445 waypoints is behind the vehicle at activation. On
1061 the target appears at the left edge while proposals stay near the prior
point and the vehicle passes it. Artifact:
`reports/paper_implementation/GEMMA_FLOW_DIAGNOSTIC_20260907.json`.
**Hypothesis.** Supplying a numeric previous-goal point biases the policy into
echoing that point instead of reconsidering the current image. Correlation
alone is insufficient: a matched intervention is required.
**Decision.** Add opt-in `previous_goal_prompt=false` in a Gemma-only development
profile. Keep internal goal projection, provenance, monitor memory, controller,
verifier, schedule and model unchanged. The prompt explicitly requests a fresh
image choice and supplies no previous-goal coordinates. Default remains true
for reproducible frozen baselines.
**Gate.** Run development seeds 1060–1064, require improved actual navigation
without false stops/collisions, and replay steering. No privileged inputs.
This experiment is not an accepted navigation fix until that evidence exists.


### D-75 — Probe image detail before changing navigation logic again
**When.** 2026-09-07.
**Evidence.** On the same unmodified baseline source frame (1061, observation
480), Gemma answers absent to plain target-description and region questions,
and emits image center for both full policy and simple coordinate prompts.
Offline replay shows a narrow visible target at the left. D-74's first three
flights still time out despite substantially reduced waypoint copying.
**Decision.** Diagnose image-detail sensitivity using fixed full-frame scaling
and a uniform four-quadrant view. No detector, truth-based crop selection,
annotation, or goal information enters the model. Use the same model and
source frame. These are diagnostic probes, not navigation results; do not
change the active profile without a matched flight gate.


**D-74 outcome.** Cue removal reduced within-one-pixel echo from 405/418 to
17/430. Navigation stayed 0/5, all timeouts, zero collisions/false stops/parse
errors. Every replay matched stored final distance exactly. This profile is
rejected as a navigation fix and remains a diagnostic ablation. Validation:
288 unit/contract tests, changed-file Ruff (excluding two pre-existing OnFly
rules), and diff whitespace check pass. Latency is not an isolated benchmark:
small same-model probes shared the server during this sweep.

### D-76 — Investigate Windows Gemma vision projector before more flights
**When.** 2026-09-07.
**Evidence.** Gemma says absent even on a close-view frame containing a large
red rectangle (visually inspected exact encoded input). Full policy and simple
point requests return image center; free descriptions hallucinate unrelated
scenes. The generate endpoint used by drone_control reproduces the distant-frame
chat results. Uniform crops/enlargement did not help that diagnostic frame.
The local Ollama log contains `F16->F32 promote tensor=v.patch_embd.weight`
with 2359296 bytes in the unified Gemma projector path.
**External evidence.** Ollama's open Windows issue and pending fix describe
this exact conversion as breaking E2B/E4B image processing outside Apple:
https://github.com/ollama/ollama/issues/16532
https://github.com/ollama/ollama/pull/16879
Read on 2026-09-07; the PR is open, not an installed fix.
**Interpretation.** This is strong evidence of a local runtime vision defect,
not proof that navigation will work after repair. D-72 and D-74 numerical
results remain preserved, but should not be interpreted as clean Gemma visual
capability comparisons until the runtime passes actual recognition controls.
**Decision.** Pause further navigation sweeps. Keep Gemma selected. Stage a
reversible runtime repair or supported same-model projector path, first check
close/absent visual controls, then re-run the Gemma baseline and navigation
experiments. Do not restart the shared Ollama server or interrupt valley work
as a routine diagnostic step. Do not add another model.
**Artifacts.** `GEMMA_CLOSE_VIEW_INPUT_20260907.png`,
`GEMMA_CLOSE_VIEW_PROBE_20260907.json`,
`GEMMA_PROJECTOR_LOG_EXCERPT_20260907.txt` and the other interface probe JSONs
under `reports/paper_implementation/`. Navigation remains unresolved.


### D-77 — Stage an exact-weight split vision projector
**When.** 2026-09-07.
**Evidence.** Installed-version v0.33.3 source unconditionally promotes the
unified Gemma vision patch embedding to F32. Upstream PR #16879 restricts
that conversion to Apple. Installed E2B stores that tensor as F16.
**Decision.** Extract a standalone clip/gemma4v projector from the installed
Gemma blob using the same metadata translation, omitting the erroneous
promotion. Preserve each vision tensor's bytes, dimensions and type and
verify hashes after writing. Do not alter the installed blob or language
weights. This is a runtime workaround for the same model, not a model swap.
Stage it offline before any runtime mutation. Validate recognition before
claiming repair; keep a rollback path if later activated.


**D-77 validation.** The split vision projector preserves all 659 vision
tensors byte-for-byte. Same-image tests now recognize the close red rectangle,
the distant red object at the left, and correctly report the absent-target
view. The original packaged model failed both positive controls. This verifies
a local visual-processing improvement; coordinate and navigation competence
remain separate gates. A first unchanged-policy flight is in progress.
**Shared-model preservation.** Also stage a combined vision/audio projector
using the upstream metadata/rename mapping, including its audio bias-name
correction. All 1,411 multimodal tensors retain their original values, types
and dimensions. This avoids discarding audio in a later shared-model repair;
audio task quality is not established by tensor checks. Do not change the
shared tag until the combined package passes the same visual controls.


### D-78 — Activate the same-weight repair under the shared Gemma name
**When.** 2026-09-07.
**Evidence.** Combined vision/audio package passes the close-visible and absent
visual controls with the same responses as the vision-only repair. All 1,411
multimodal tensors are verified unchanged (renames only for audio compatibility).
The language-model layer digest is identical. Audio quality is not evaluated.
**Decision.** Preserve the old manifest under
`gemma4:e2b-before-projector-fix-20260907`, then point `gemma4:e2b` at the
repaired package so C5 and valley share one model name and resident weights.
No server restart or service replacement. Keep historical config digests
unchanged and override the new digest only in repaired development profiles.
**Next navigation gate.** The first unchanged-policy repaired flight stopped
14.356 m from the goal, zero collisions. Re-test the already implemented
target-bound arrival check on development seeds 1060–1064 with repaired Gemma.
Runtime repair does not establish navigation success.


### D-79 — Probe a marked-image grounding interface
**When.** 2026-09-07.
**Evidence.** Repaired-runtime target-bound seed 1061 times out without false
stop/collision. Exact replay shows 36 target-visible policy frames, but closest
approach is 13.22 m; 47/81 proposals still echo the numeric history cue.
**Decision.** Before another control change, probe uniform numbered image
points with Gemma on saved close, distant and absent views. The model chooses
an ID; calibration maps it back to an image point. Marks are uniform and use
no detector, goal truth, semantic crop or scripted target search. This tests
the output interface, not navigation success. Do not promote without flights.


**D-78 gate outcome.** Repaired-runtime target-bound profile: 0/5. Seeds 1060
and 1064 falsely stopped at 25.045 m and 28.754 m; the other three timed out.
No collisions or monitor parse errors. The depth check cannot verify semantic
identity when the VLM points to the wrong nearby surface.
**D-79 outcome.** Uniform marks identify the distant target but miss the
close target's body. A description-first schema improves one positive
visibility answer but still marks a gray surface as the red target. No
marked-point or prompt-only variant is promoted.

### D-80 — Depth-region proposals with VLM semantic selection
**When.** 2026-09-07.
**Rationale.** Free coordinates are unreliable even after visual runtime
repair; geometry must bind the semantic selection to an actual surface.
**Decision.** Prototype generic connected depth regions and show their RGB
crops with candidate IDs to Gemma. The model selects the requested object or
none; the chosen region supplies an in-region sensor pixel and range. Candidate
creation reads only calibrated depth, never RGB colors, target labels or
simulator objects. All visible depth regions are treated identically. This is
not scripted target search and does not add a second learned model.
**Gate.** Check visible and distractor-only frames before implementation in
C5, then evaluate navigation with no truth exposed to the policy. This is a
provisional interface experiment, not an accepted fix.


### D-81 — User-authorized Gemini Flash free-tier comparison
**When.** 2026-09-07.
**Decision.** User requests a brief Gemini Flash comparison, limited strictly
to free use. This permits a temporary cloud-model comparison despite D-73's
Gemma default. Keep the local Gemma runner available for valley. Use matched
recorded frames first, then matched development flights if grounding passes.
Stop at the first quota/rate-limit response; no automatic retries, model
fallback or paid tier. Confirm that the credential belongs to a free-tier
project before calls; HTTP 429 alone is not a spending limit on a paid project.
**Current state.** No Gemini key found in process/user/machine environment or
the referenced drone_control .env file. No Gemini API calls made. Need the
location of a free-tier credential; never print or store key values in reports.


**D-81 credential configuration.** User supplied the keys directory and asked
for a .env referring to existing key files. The ignored project .env points
GEMINI_API_KEY_FILE at keys/gemini_key.txt; no secret is copied into the repo.
The probe resolves that file at call time, sends the key in an HTTP header,
and never prints it. Calls require confirmation that project billing is
disabled; quota exhaustion persists a local stop marker with no retries.

**D-81 billing confirmed.** User confirms billing is disabled. The comparison uploads only synthetic simulator RGB frames. The close-view PNG is generated by tmp/export_close_actual.py from deterministic scene 1061, not a personal screenshot or document.


### D-82 — Matched Gemini Flash C5 comparison
**Evidence.** Gemini 3.5 Flash passes three same-prompt/schema recorded-frame
grounding checks: distant target at (93,359), absent view false/null, and the
Gemma false-stop view false/null. Artifact: GEMINI_MATCHED_GROUNDING_20260907.json.
**Decision.** Add an opt-in Gemini backend and compare the existing target-bound
C5 profile, changing only the inference model/backend. Keep fixed simulated
policy/monitor latency 1.0/1.2 s, report measured cloud time separately. Start
with development 1061; any 429 aborts calls persistently, no retry or fallback.
A quota-interrupted flight is not a completed navigation result. Gemma remains
the active local default and available to valley.


**D-82 execution outcome.** The 1061 comparison stopped at the first HTTP 429, at 4.0 simulated seconds, with a persistent quota marker and no retries. This is an interrupted experiment, not a navigation failure or success. See GEMINI_C5_QUOTA_SCREEN_20260907.json and the retained run events. All 295 unit/contract tests and focused Gemini lint checks pass. The three matched grounding checks support only image-level improvement; navigation remains unresolved. No further Gemini requests are permitted under this comparison after the quota stop.


### D-83 — User-requested fresh Gemini run, 2026-09-10
**Decision.** User asks to run the comparison again, superseding the D-82 no-retry instruction for one fresh attempt. Archive the previous quota marker; retain the same first-429 stop, no automatic retry or paid fallback. Use development seed 1061 and the unchanged comparison profile. Billing-disabled confirmation remains in force; upload only synthetic box-world frames.
**Evidence.** Prior attempt was quota-interrupted; new outcome pending.

**D-83 outcome.** Fresh run stopped on Gemini HTTP 503 after 2.0 simulated seconds; 3 inference calls completed. No retries or paid fallback. This is a service-error interruption, not a navigation result. Artifact: GEMINI_C5_SCREEN_20260910.json.


**D-83 second user-requested attempt.** Gemini again returned HTTP 503, this time after 10 simulated seconds. No automatic retry. Retained run: c5_gemini_flash_20260910_retry2_s1061.

### D-84 — Explicit free-provider failover
**Decision.** User requests routing among Gemini, Groq, Mistral and OpenRouter. Add an opt-in backend retaining the current provider until transport failure; then disable that provider for the run and try the next confirmed free provider once. Persist 429 blocks across runs, respect the existing Gemini quota marker, never clear blocks automatically, never use paid OpenRouter model IDs, and stop when routes are exhausted. Missing credentials or free-only confirmation disable a provider. Log actual provider/model and failed attempts; mixed-provider flights are a distinct development architecture, not a single-model comparison. Keep Gemma default and its resident runner unchanged.
**Evidence.** Only Gemini credential file is currently available. Groq official vision documentation lists qwen/qwen3.8-27b; Mistral lists mistral-small-2506; OpenRouter supports explicitly free variants. Live non-Gemini validation awaits keys and confirmation. Mocked failover/transport tests required.

**D-84 implementation check.** 306 unit/contract tests pass, including 11 new router/transport tests. Focused Ruff checks pass. Added disabled provider placeholders to ignored .env and .env.example. No non-Gemini API calls made; multi-provider live test awaits keys, free-access confirmation and a pinned available OpenRouter vision model.

**D-84 credential paths.** User supplied Groq and OpenRouter files and explicitly prohibited reading their contents. Listed filenames only and configured GROQ_API_KEY_FILE to keys/groq llm.txt and OPENROUTER_API_KEY_FILE to keys/openrouter.txt in ignored .env. Verified file existence only. No key contents read or API calls made. Existing free-access flags remain unchanged.

**D-84 single simulation authorization.** User requests one simulation without quota-consuming probe tests. Public unauthenticated OpenRouter catalog confirms google/gemma-4-26b-a4b-it:free accepts images and has zero prompt/completion prices; enable that pinned route with existing zero-price request caps. Gemini remains billing-disabled. Groq remains disabled unless user confirms free-only billing. No key contents inspected and no preliminary inference probes.

**D-84 single-run outcome.** Gemini returned 429 and the router switched once to OpenRouter gemma-4-26b-a4b-it:free, which also returned 429. Two failed provider attempts, no successful inference, no probe calls or automatic retries; stopped before movement (0 simulated seconds). Both quota stop markers persisted. Groq/Mistral were disabled. Artifact: FREE_ROUTER_SCREEN_20260910.json. No navigation conclusion.


### D-85 — Literature and implementation audit before further navigation trials
**When.** 2026-09-10.
**Decision.** Retain the basic task. Treat current C5 results as configuration-specific failures, not a demonstrated failure of the family or planning generally. Prioritize a zero-inference trace of goal bearing, path-carrot bearing, yaw, grounding and visibility. Any controller intervention needs a separate opt-in implementation decision preserving frozen profiles.
**Rationale.** Published methods depend on spatial/action interfaces. Local goal-facing yaw is absent, but its causal role remains untested. Repaired Gemma still has grounding errors. C1 gets labeled metric observations, preventing an equal-input LLM/VLM planning conclusion.
**Evidence.** docs/research/c5_navigation_audit_20260910/REPORT.md; 41 screened candidates and 24 primary works. Exact offline seed 1061 replay: target visible in 36/89 decision frames, median visible-frame center error 30.13 px, closest decision distance 13.22 m. These measurements do not prove yaw caused failure. No model calls, flights or navigation code changes.
**Status.** Research complete; navigation unresolved. Existing quota and held-out restrictions remain in force.


### D-86 — Isolated goal-facing yaw development ablation
**When.** 2026-09-11.
**Decision.** User authorizes D-85 trace and conditional yaw trial. Add an opt-in controller parameter that faces the planner-recorded semantic goal, preserving velocity, limits, recovery actions, model, prompts and frozen defaults. One repaired target-stop Gemma seed 1061 flight only; no provider API, other models or held-out seeds.
**Rationale.** Exact offline replay identifies target loss at 58.8 s with motion/semantic divergence 152 degrees while semantic bearing differs from target by 0.37 degrees. Other losses also involve grounding or occlusion; yaw is not a complete explanation. Predicted pixel is outside the red-body bbox in all 36 visible decision frames (bbox score, not full-object semantic accuracy).
**Evidence.** docs/research/c5_navigation_audit_20260910/yaw_trace_1061.json; exact distance replay. Motion direction is a carrot-direction proxy when tracking, not a reconstructed trajectory. Existing baseline reused; new run is a historical-baseline development comparison, not deterministic paired replication.
**Status.** Provisional diagnostic only. Compare visibility, closest distance and terminal success; no automatic five-seed expansion.


**D-86 outcome.** One goal-facing yaw trial failed by false stop at 63.2 s, 25.20 m from target; closest 24.74 m, zero target-visible replay frames and no collisions. Baseline closest 13.22 m and 36.4 s visible. Both exact replays match final distance; actual model Gemma E2B verified. Manifest differs only in yaw option and identifying labels. 308 unit/contract tests and focused lint pass. Do not promote or expand: yaw alone is insufficient; investigate false target identity and stop evidence offline. Historical-baseline comparison is not a controlled estimate of model stochasticity. Report: docs/research/c5_navigation_audit_20260910/YAW_RESULT_20260911.md.


### D-87 — Current-frame grounding monitor, bounded autonomous session
**Decision.** User authorizes four to five adaptive development flights with commits. First isolate monitor grounding: one latest image, short describe-then-identify schema; arrival remains synchronized target-pixel depth plus distinct-frame geometry. No mission-specific color detector, truth, scripted search or new backbone. Keep yaw off. Up to five flights total this session; record each result before selecting the next change.
**Rationale.** Exact false-stop frame is a gray obstacle. Existing monitor conflates multi-image history, identity, apparent scale and status and contains conflicting one-field/six-field output instructions. Geometry consistency cannot validate identity. Prior simple grounding rejected an absent frame but missed a distant target, so navigation improvement is not assumed.
**Status.** Opt-in development only, not a faithful source reproduction or accepted fix.


### D-88 — Explicit target versus exploration waypoints
**Decision.** Prepare an opt-in fresh-evidence policy interface: model describes the current view briefly and labels its point target or exploration. Only target points receive the mission target label. Exploration remains model-selected; no fixed heading, privileged coordinates or color detector. Remove the previous point from this variant's prompt to test the observed copy tendency. Monitor and planner remain the D-87 configuration. Run only after flight 1 is scored.
**Rationale.** Legacy policy conflates navigation points with target-labeled waypoints and often echoes the supplied point. Target-bbox metrics were consequently ambiguous. New provenance makes the policy's claim explicit and auditable. This is a combined interface ablation, not a single-factor attribution.
**Status.** Development candidate, no assumed success.


**D-87 run 1 outcome.** Seed 1061 timeout, final 14.15 m, no collisions or false stop; 38 visible decision frames, monitor accuracy 37.8%. Exact replay error zero. Identity remains unreliable. D-88 will be run next; no default promotion.


### D-89 — Check declared attributes before selecting a target
**Decision.** Add opt-in semantic color consistency to D-88 policy and D-87 monitor. For instructions with exactly one explicit supported color, require the VLM-reported candidate color to match it. The policy also provides an exploration alternative in the same call; a mismatched candidate cannot become a target and selects that model-proposed alternative. Monitor mismatch cannot establish acquisition or STOP. Ambiguous/multicolor instructions are rejected by this opt-in mode rather than guessed.
**Rationale.** Flight 2 explicitly describes a gray rectangular building while labeling it target. This is a contradiction in model outputs, not absent visual information. The guard compares language attributes only: no RGB thresholding, simulator truth, scripted search or extra learned model. Color recognition remains the VLM's responsibility and hallucinated matching colors can still fail.
**Status.** Task-contract-limited experimental semantic verifier, not a faithful OnFly reproduction. Run after flight 2 is scored; keep frozen defaults.


### D-90 — Retain monitor guard, restore original waypoint policy
**Decision.** For the remaining bounded trials, isolate the current-frame/color-consistent monitor with the original waypoint policy (yaw off). D-88/D-89 policy variants remain opt-in records, not defaults. Compare on 1061, then check the selected monitor on 1060 if no new blocking defect appears.
**Rationale.** Flight 2 regressed to 40.25 m final distance; flight 3 is rejecting gray/green target claims but its model-selected exploration travels away from the goal. The guard fixes a semantic contradiction but does not make exploration useful. Restore the stronger prior policy instead of stacking additional untested planning machinery.
**Status.** Candidate monitor fix only; no claim of solved navigation or general capability from one seed.


### D-91 — Final bounded trial: remove only previous-point cue
**Decision.** If D-90 seed 1061 fails, use the fifth and final flight for the same profile/seed with previous_goal_prompt=false. No new policy schema or exploration mechanism. If D-90 succeeds, use the final flight to check D-90 on another development seed instead.
**Rationale.** During D-90, 31 of 50 comparable decisions copy the previous point within one pixel. D-88 changed several interface factors and regressed; this isolates only the continuity cue with the repaired runtime and guarded monitor. Copying can also reflect valid persistence, so improvement is not presumed.
**Status.** Budget ends after flight 5 regardless of outcome. No default promotion without evidence beyond one development seed.


### D-92 — Correct offline monitor image alignment
**Decision.** Score monitor visibility against evidence_observation_seq, not its response/activation time. Missing source IDs are unscored and counted. Recompute all five saved-trial monitor metrics without inference.
**Rationale.** Offline analyzers previously compared the delayed answer to the control frame at completion; the camera can move during that delay. Published intermediate visibility accuracies in D-87/D-90 and commentary are superseded by source-aligned values. Navigation success, final distance and exact control replay are unaffected.
**Evidence.** Regression fixture changes visibility between source and completion frames. Both analyzers now use the logged source observation identifier.


### D-93 — End bounded session; no navigation promotion
**Decision.** Five authorized adaptive trials on development seed 1061 are complete, all timeouts. Keep the original active profile. Retain tested diagnostic fixes and opt-in variants for reproducibility; no further flights or calls scheduled.
**Evidence.** Final distances 14.15, 40.25, 72.45, 14.62, 77.18 m; zero collisions or premature stops. Source-aligned trial-4 monitor TP=3/FN=6/FP=0/TN=36. Three saved-image recognition calls reject a gray negative but also the clear red approach and solid-red arrival views. See AUTONOMOUS_DEBUG_20260911.md and AUTONOMOUS_RUNS_20260911.json. 323 unit/contract tests and focused lint pass; baseline plus all trial distance replays exact, all source monitor frames matched.
**Rationale.** Semantic contradictions can be guarded in code, but useful exploration and positive target recognition remain unresolved. Fewer false claims alone is not a solved monitor. Before more flight tuning, require a passing fixed positive/negative image-grounding gate; this is not yet a defensible general planning failure claim.


### D-94 — Shared flight debugger before more navigation changes
**Decision.** Build an offline, synchronized flight debugger with map, replay camera,
observer view, decision timeline, proposed/accepted actions, VLM request/response
inspection and code locations. Start with saved development runs; no inference.
Add opt-in diagnostic recording for exact future requests, images and outputs.
**Rationale.** User cannot inspect the causal chain through scattered logs and
static images. Agree on the first observable mismatch before proposing another fix.
**Evidence.** Existing events preserve controls and source-observation IDs but omit
raw prompts/responses and full paths. The drone_control dashboard provides the
interaction reference. Old unavailable evidence must remain explicitly missing;
reconstructed views and current-code references must be labeled. Replay must
validate all available logged positions and the final distance; truth overlays
are diagnostic only. No change to model, policy, controller or experiment defaults.
**Status.** Implemented. Portable HTML built from three saved development flights;
5,305 positions and three final distances match exactly, all 396 source frames
matched. 335 unit/contract tests and browser interaction checks pass. No model
calls. The debugger explicitly supports grid3d without injected failures; this
simulator-specific diagnostic is registered in the portability contract test.
Opt-in `--debug-capture` preserves exact requests/returned outputs, source
snapshots and full paths; default experiment behavior is unchanged. User guide:
`docs/FLIGHT_DEBUGGER.md`. Inspect a shared moment before selecting another test.


### D-95 — User-directed physical passage probe at 41.60 seconds
**Decision.** Restore the exact state of c5_guarded_monitor_20260911_s1061
at t=41.60 s / observation 833 by replaying all preceding controls. Preserve
position, velocity and yaw. From that state, issue a manual forward command
and a separate command toward the visible opening center. Stop at first
collision or after clearing the obstacle pair, with a bounded duration.
**Rationale.** User identified a concrete visual bottleneck and explicitly
requested a physical crossing attempt. Test the observation directly before
arguing about the VLM or modifying navigation.
**Evidence.** Pending execution. No VLM calls, no changes to the deployed
planner, controller, model or safety settings. Manual bypass of the planner is
only a physical diagnostic, not evidence of autonomous navigation success.
Scene truth may measure the result; this probe is privileged_diagnostic and
must never enter the paper's architecture performance tables.


**D-95 outcome (2026-09-12).** Both branches restored observation 833 with
zero positional replay error and identical original velocity/yaw. Forward at
82.05 degrees collided with the left obstacle after 9.85 s; the probe stopped
at the first collision flag. Aimed at visually chosen image column 128/224
(bearing 74.01 degrees, 8.04 degrees right), the same 0.6 m/s command cleared
both obstacles in 19.50 s without collision. Minimum sampled wall distance from
body center was 0.613 m, leaving 0.213 m beyond the 0.4 m body radius. The
planner clearance parameter is 1.8 m. This establishes physical fit with altered
aiming, not planner acceptance or the causal explanation of the original stall.
Obstacle staggering matters; projected slit width is not a constant corridor
width. No VLM calls or runtime changes. Videos, exact traces and report:
`reports/passage_probe_20260912/REPORT.md`; browser comparison:
`reports/debugger/passage_4160.html`. H.264 video playback verified in Edge,
with no JavaScript errors. Implementation/script checkpoint: 2a8f489.


### D-96 — Fixed destination through the disputed opening with SUPER active
**Decision.** Run one bounded privileged diagnostic from guarded Gemma seed
1061 at t=41.60 s / observation 833. Restore physical state by exact control
replay and reconstruct SUPER's prior replans from saved model pixel coordinates
and synchronized depth. Validate historical plan metadata before continuation.
Give the unchanged planner/router/controller a fixed metric destination equal
to the successful D-95 opening probe endpoint (20.7940515013, 21.7478134662,
2.4739341311) m. Refresh that same intent every 1 s, matching the original
observed policy availability interval; control remains 20 Hz. Retain nominal
1.8 m planner inflation. Stop at first collision, within 0.5 m of the waypoint,
or at original t=90 s (48.4 s continuation). No model calls.
**Rationale.** Separate local execution toward a persistent destination from
repeated VLM pixel selection and depth lifting. Reconstruct recent occupancy
and route continuity rather than silently replacing them with a cold start.
**Evidence.** D-95 establishes a physically possible manual crossing. It does
not establish that SUPER can choose and execute it under the current settings.
This test replaces semantic policy, monitor and image-point verifier with an
explicit manual metric goal; it measures the local execution boundary only.
Map/clearance truth is for evaluation and drawing, never passed to SUPER.
**Scope.** Preserve frozen reference configurations. A future candidate-route
ranking or verification component is a named architecture variant/ablation,
not a silent improvement attributed to a reproduced paper. No such component
is implemented by this decision. See ARCHITECTURE_FAMILIES.md for the existing
hybrid/verifier search space.
**Status.** Preregistered; execution pending. Diagnostic only, excluded from
architecture performance tables.


**D-96 outcome (2026-09-12).** The single continuation reached within 0.489 m
of the fixed waypoint in 38.10 s, with no collision. SUPER selected a 21.83 m
wide detour around the right obstacle; all 39 replans accepted. Minimum sampled
body-to-wall gap was 0.949 m. Restoration matched all 833 positions/controls
exactly, all 41 historical plan metadata records and all 41 source depth lifts.
The original active waypoint at this state was only 0.378 m away. No model
calls or runtime/parameter changes. This shows the local stack can progress
with a useful persistent goal here; it does not isolate pixel selection, depth
lifting, update persistence or monitor effects. No terminal stopping or red-tower
arrival was tested. Next inspect the source-pixel to accepted-waypoint handoff.
No verifier was added; new route-ranking work remains a separately named
architecture variant under the design document's frozen execution constraints.
Report: `reports/super_passage_probe_20260912/REPORT.md`; portable interactive
replay in that folder; local preview `reports/debugger/super_passage_4160.html`.
Script lint, trace checks and Edge replay interactions pass. Diagnostic only;
never include these results in autonomous architecture performance tables.


### D-97 — Offline visual audit of the waypoint handoff
**Decision.** Replay the saved guarded Gemma development flight without
inference. Reconstruct each saved policy point from its exact source pose,
image and depth. Inspect the approach/stall window (24–50 s availability),
including decision 3bec7cd30542 active at the user's 41.60 s cursor.
Display source pixel, 5x5 depth sample, lifted/accepted waypoint, local paths
and subsequent replacements together. Independently compare obstacle depth
with ray/box intersection so a sensor defect is not mislabeled as model error.
**Rationale.** D-96 established local execution capability with a persistent
manual destination but changed multiple upstream mechanisms. Locate the first
observable contract mismatch before selecting a navigation change.
**Evidence.** Pending replay/audit. The existing depth renderer paints a whole
box silhouette with its minimum positive corner depth; whether that materially
changes the selected waypoints requires measurement. All geometry truth is
restricted to diagnostic evaluation. No VLM calls, new autonomous flights,
reference changes or route verifier are part of this audit.
**Status.** In progress; offline diagnostic, not a benchmark result.


**D-97 outcome (2026-09-12).** Confirmed depth contract defect, before any
navigation change. At decision 3bec7cd30542, source 39.95 s, the selected
obstacle-7 pixel receives 0.213216 m from an off-screen corner instead of the
1.732390 m surface depth along its camera ray. The 5x5 median/gate/lifting
propagate that bad sensor value. First selected-box mismatch in this flight
is available at 18 s; in the disputed approach it affects uncapped waypoint
range from 30 s. Source pixels select obstacle 7 during 26–42 s. Accepted
world goals during 32–41 s lie within 0.116146 m of each other, narrowing the
hypothesis that repeated replacement canceled a useful distant goal during
that phase. D-96's goal was also different/farther, not merely persistent.
All 1,800 historical controls/positions, 89 plans and 89 full source depth
ownership reconstructions match. Four analytical ray cases, 46 hit/reprojection
checks, two existing camera tests, script lint and Edge UI checks pass.
No model calls, new autonomous flights, runtime edits or verifier changes.
Next fix the shared per-pixel depth contract with preserved historical replay,
then validate the same pixels offline before testing navigation. This does
not establish that sensor repair alone solves wall selection or the mission.
Evidence: `reports/waypoint_handoff_audit_20260912/REPORT.md`; local visual
page: `reports/debugger/waypoint_handoff.html`. Status: audit complete.


### D-98 — Versioned per-pixel obstacle depth repair and one matched flight
**Decision.** User authorized fixing D-97's sensor defect and running one
simulation. Add an explicit `box_ray_v2` depth renderer: camera-forward
ray/box intersection at each pixel of the box drawn in RGB. Preserve
`legacy_corner` as the default for historical configurations/replays. Preserve
RGB painter ordering, landmark billboards, missing-background-depth behavior,
near range, controller, SUPER margins, policy and monitor settings.
**Rationale.** Repair the proven source-depth error while isolating its effect
from semantic architecture changes. The RGB rasterizer's other approximations
are not a new confound introduced by this repair; invalid box-ray intersections
remain missing depth rather than invented ranges.
**Validation.** Test the exact off-screen-corner failure, oblique surface depth,
near-plane/miss handling, drawn-surface occlusion, landmark behavior and legacy
compatibility. Check all saved source pixels and preserve historical replay.
**Run.** Exactly one development flight from launch, seed 1061, 90 s horizon,
architecture `c5_gemma_guarded_monitor_dev`, local shared `gemma4:e2b`, debug
capture on. New environment inherits `grid_nav_onfly_native_dynamics` with
only `depth_renderer: box_ray_v2` changed. No API providers, model swap,
margin tuning or adaptive reruns. Compare with the original guarded flight;
one seed can show a diagnostic effect but cannot establish general success.
**Status.** Preregistered, implementation and validation pending. All changes
and run outcomes go in CHANGES.md and separate commits.


**D-98 preflight validation.** Implemented explicit `box_ray_v2`; historical
`legacy_corner` remains unchanged. All 342 unit/contract tests pass. Saved
source check retains 1,800 poses and 89 original RGB/depth images exactly;
1,146 corrected box patch pixels match independent geometry within 4.75e-7 m.
The disputed patch median is now 1.731457 m instead of 0.213216 m. RGB rendering
and architecture config are unchanged; the only environment parameter change
is the depth-renderer version. Saved-pixel corrected waypoint still points at
the selected wall. One launch-to-90 s Gemma flight is now ready to test the
behavioral effect, with no claim that sensor repair must solve navigation.


**D-98 flight outcome (2026-09-12).** Completed exactly one corrected-depth
Gemma seed-1061 flight, with all other configuration fixed and debug capture.
Timeout at 90 s, no collisions. Final target distance 30.01488 m versus original
14.61545 m; closest 14.93985 m versus 14.32356 m. New path length 50.59676 m,
original 32.31351 m. All 89 proposals accepted; 89 policy and 45 monitor calls,
all actual `gemma4:e2b`, local only. First changed pixel at 19 s after the
changed depth at 18 s; trajectory divergence starts 28.05 s. New closest
approach occurs at 40 s, followed by departure. Sensor correction is validated;
this flight does not establish improved navigation. Preserve corrected mode
and historical replay; no architecture promotion, adaptive retry or new call
scheduled. Both 1,800-pose replays and final distances match exactly. Exact
calls/source images/paths captured, Edge comparison checks pass. Report:
`reports/depth_renderer_fix_20260912/REPORT.md`; watch
`reports/debugger/depth_fix_comparison.html`. Fix checkpoint `ebaa1bd`.


### D-99 — Two additional corrected-depth development flights
**Decision.** User requested two more flights after viewing D-98. Run exactly
seeds 1060 and 1062, once each, using c5_gemma_guarded_monitor_dev with
grid_nav_onfly_depth_v2_dev (90 s), shared local gemma4:e2b and debug capture.
**Rationale.** Add two development layouts to the existing seed-1061 result.
Identical-seed repeats with temperature zero, fixed sampling seed and fixed
simulated latency would primarily test reproducibility. Different seeds test
whether the observed navigation failure also occurs in other layouts. Initial
commentary suggested the same seed; this was corrected before any flight.
**Evidence.** D-98 validates sensor geometry but its one flight times out.
No runtime/config changes or adaptation between these two flights; no cloud
calls, model changes, held-out seeds, added verifier or automatic third run.
Compare outcomes and exact visual replays for all three corrected-depth seeds.
This is a small development screen, not a matched legacy-versus-fixed claim
on the two new seeds or a general architecture conclusion.
**Status.** Preregistered; two requested flights pending. Preserve each result
and commit it before proceeding to another change.


**D-99 first flight (seed 1060).** Completed once: timeout at 90 s, final
59.26628 m from target, path 49.86468 m, zero collisions, 89 accepted proposals.
All 134 completed inference events use gemma4:e2b; no inference/parse errors.
Architecture and environment manifests exactly match D-98. Full debug capture
saved; exact replay and closest approach will be checked in the final export.
Preserved result, manifest and console log. Added a zero-inference four-run
comparison exporter; script lint passes. Seed 1062 is the remaining authorized
flight; no parameter changes before it.


**D-99 outcome (2026-09-12).** Both authorized additional flights completed,
unchanged configuration: seed 1060 timeout, closest 26.24 m at 24.50 s, final
59.27 m; seed 1062 timeout, closest 21.22 m at 39.45 s, final 37.46 m. Each
90 s, zero collisions, 89 accepted proposals and 134 completed actual local
Gemma calls; no inference/parse errors. Corrected-depth development total is
0/3 including D-98, not a general architecture estimate. Exact config matching
passes. All four debugger replays reproduce 1,800 positions each, final distance
and 89 policy sources; no missing frames. Browser selection, seeking, new-flight
playback and raw responses pass, zero JavaScript errors. Inspected closest/final
maps and camera views: approach then departure, without assigning model intent.
Evidence: reports/depth_renderer_two_runs_20260912/REPORT.md. Comparison page
now includes the two new flights, prior corrected 1061 and historical legacy
1061. Keep depth repair; inspect source-aligned departure decisions next. No
further flight or inference scheduled. Status: requested two-run screen complete.


### D-100 — Audit drone_control and specify a graph-selector comparison
**Decision.** User authorized examining drone_control's frontier/viewpoint system
and defining the next comparison. Preserve C5 as end-to-end context; propose two
named graph variants with identical candidate generation, grounding, memory and
execution, differing in classical versus local Gemma candidate selection. This is
a design decision, not a runtime implementation or authorization for more flights.
**Rationale.** D-99's 0/3 corrected-depth outcomes do not isolate planning quality.
A shared discrete, executable candidate interface permits matched choice diagnostics
and exposes which decisions the model actually owns. Reuse the existing source
mechanisms before inventing another full stack.
**Source findings (verified by inspection, not flight).** At drone_control commit
070f2da, frontier_graph_yolo's GraphSearchSession calls classical ViewpointGraph
selection; the mission planner can call an LLM at the mission level, but recognized
instructions can return heuristic plans before inference. Separately, HierarchicalAgent
supports VLM region-ID selection and an optional frontier menu, default OFF. Frontier
IDs are re-enumerated per menu and reachability exceptions fail open. The graph
and the VLM-menu paths must not be presented as one proven LLM graph planner.
**Comparison contract.** Shared observation-derived geometry, stable candidate IDs,
source/map revisions, viewing yaw, visited/failed state, target evidence and goal
commitment. Keep task, dynamics, SUPER and stopping criteria. Geometry and shared
image-derived grounding are offline gates before flights; no adapter semantic_hits,
privileged goals/maps, source arena biases or source motion constants. The two graph
arms isolate selector choice; graph versus C5 changes multiple architecture components.
A classical selector with shared VLM perception is not an entirely model-free system.
**Evidence.** docs/research/drone_control_graph_comparison_20260912/REPORT.md and
SOURCE_AUDIT.json (source hashes and checked line ranges), plus the existing validated
24-primary-work D-85 review. No new external implementation-availability claims.
**Status.** Audit and design complete; implementation/navigation unverified. Next
build typed candidate snapshots, stable identity and an observation-derived map
adapter; display candidates and route evidence in the debugger before model trials.
No code changes in drone_control or either runtime, no new model calls or flights.


## D-101 — VLM-authored adaptive planning (2026-09-12)

Status: component adaptation implemented; offline checks pass; real-model/flight validation pending.
Supersedes D-100 next implementation direction, not its source audit.
Rationale: user requires the VLM to author intermediate navigation goals and order.
Select MapGPT adaptive-plan carryover with existing SPF image-point/travel mapping;
retain shared execution, name the hybrid explicitly and record all deviations.
Evidence: docs/research/vlm_authored_planning_20260912/REPORT.md, evidence.json and
search_log.md; 24 prior plus 3 new primary methods, official planning code inspected.
No autonomous performance claim.

D-101 implementation evidence: `reports/adaptive_visual_plan_20260912/REPORT.md`
and `VALIDATION.json`; 361 unit/contract tests, 17 new policy tests, 8 GUI checks.
Model owns plan/order/point. No runtime model calls or autonomous flight results.
OnFly depth-equality verifier replaced only in the new SPF-based profile; shared
execution unchanged. Future C5 comparison is end-to-end, not an isolated planning
causal test. Source-audit hash comparison required only Windows newline normalization.


## D-102 — Adaptive-plan flight and visual diagnosis (2026-09-12)

Status: preflight, one flight and dashboard diagnosis complete; fixes unimplemented.
Rationale: validate D-101 on real Gemma and inspect the actual flight in the dashboard.
Evidence: reports/adaptive_plan_flights_20260912/PLAN.md preregisters a bounded
preflight/flight/fix budget. No performance conclusion yet.

D-102 outcome: timeout 90 s, zero collisions, closest/final 23.995 m. 71 verifier
rejections; model continues the same semantic plan despite receiving feedback.
Copied historical SUPER accepts exact rejected goals at 19 and 32 s. This establishes
admission disagreement plus model non-adaptation, not a VLM-only failure or proof of
physical success with a relaxed gate. Evidence: reports/adaptive_plan_flights_20260912/
REPORT.md, DECISION_AUDIT.json, REJECTION_PROBE.json and dashboard captures. No runtime
fix or second full flight; no general planning-performance conclusion.


### D-103 — Eight capability scenarios in the shared local simulator
**When.** 2026-09-12.
**Decision.** Implement first agreed scenario in each of the eight regimes from
`general_single_uav_autonomy_benchmark_design.pdf`; research framing follows
`C:/Users/Asael/Documents/רחפנים סקירות/מסמכי דיזיין/ASP-UAV_Final_Research_Design.pdf`.
Nine refers to experimental architecture conditions, eight to capability regimes.
New adapter shares grid dynamics and corrected depth. Evaluator-only task gate
handles ordered visits, branch choice, and sustained tracking; old scoring remains
unchanged when the gate is absent. No answer-bearing semantic detections for new tasks.
**Rationale.** Capability coverage needs distinct measurable tasks, not eight renamed
point-goal missions. No model changes or inference are needed to validate scenarios.
**Evidence.** Eight scripted continuous fixtures pass collision-free; C0/SUPER
known-goal integration passes in 5.75 s. Private gate tests reject wrong order,
wrong branch, wrong vehicle, stationary following, and altitude/geofence violations.
Dynamic dashboard playback and exact task-score replay are verified. Full evidence
and validation counts: `reports/capability_scenarios_20260912/REPORT.md`.
**Status.** Implemented and mechanically validated; real-model capability untested.
No changes to existing model policies or D-102 gate behavior.


## D-104 - First capability screen (2026-09-12, in progress)

User authorized the existing three architectures on the eight D-103 scenarios.
Bound: one episode per cell, development seed 1061, 60 simulated seconds maximum,
no tuning/retry sweep, no cloud calls. Save all outcomes and full debug evidence.
C0 remains unchanged and goal-seeking: it is not an oracle task sequencer or follower.
C5 uses existing c5_gemma_ground_monitor_dev, with camera pitch calibrated from
-0.15 to -0.10 rad and no red-tower-specific color guard. This is an explicitly
named profile, not an unchanged guarded-monitor replication. Gemma digest is pinned.
C1 currently accepts text detections only; new scenarios withhold semantic hits.
User input on retaining that contract versus adding visual perception is pending.
No C1 interface change is made here. Do not compare unsupported inputs as model failures.
Rationale: measure current cross-task behavior before architecture redesign.
Evidence: scripts/run_capability_screen.py; reports/capability_screen_20260912 (pending).

D-104 continuation: C1 named Gemma profile preserves the existing text-only interface.
Only model/runtime settings change to obey the standing shared-Gemma constraint;
no camera integration or semantic-hit restoration. Its inherited 8.5 s policy charge
is preserved, versus C5's 1/1.2 s policy/monitor charges: this is a compatibility
screen, not a matched-latency or pure model-quality comparison. Awaiting any user
steering on visual integration; no new vision protocol is inferred from silence.

D-104 completed: all 24 first-screen episodes ran once. C0 6/8, C1 0/8, C5 0/8.
Evidence: reports/capability_screen_20260912/{REPORT,FINDINGS}.md, per-cell manifests/
results, call audit, closest-approach evidence, replay checks and browser screenshots.
745 completed Gemma requests, 15 boundary cancellations, no cloud. C0 events simulated.
C1 coordinate arrival/done rejection and C5 0.335 m approach/no stop invalidate a
blanket planning-failure interpretation. Six C5 cells record constraint violations;
all runs have zero collisions. 24 exact replays and 72 browser snapshots/24 playback
checks pass. No policy repair or repeat flight made; no running/scheduled work remains.
Next diagnostic scope is in FINDINGS.md; C1 visual interface question remains open.

## D-105 - AerialClaw task contract and perception tools (2026-09-13, in progress)

User authorized coordinate completion repair, then a model-requested visual perception
skill with mission/skill authority preserved. First repair aligns policy and runtime
arrival checks on the public coordinate and odometry; no simulator truth is used.
Only the declared known_goal_nav coordinate syntax is recognized, never hidden/search
goals or model-invented coordinates. Existing semantic profile remains unchanged.
Next: saved-call regression, one coordinate flight, then optical detection tool and
one visible-pillar flight. Gemma only; no OnFly edits or broad trial sweep.
Rationale: D-104 reached coordinate but rejected done for missing exact-label evidence.
Evidence: tests/unit/test_aerialclaw.py; D-104 original requests/result. New evidence pending.

D-105 outcome: public-coordinate stop repair passes one matched flight at 26.0 s.
Opt-in model-requested visual tool plus bounded local pixel refinement passes the
visible-pillar case at 35.7 s / 1.415 m, with 3 text calls + 1 image call. The first
strict-point variant failed; an unsuccessful bbox probe was not adopted. Search
remains open: first search used no detection calls; intended-strategy trial was
INVALID SETUP because a failed code insertion/test did not gate the shell chain.
Actual search advice is now corrected and offline-tested only; no third search run.
Rationale/limits/evidence: reports/aerialclaw_tools_20260913/REPORT.md and saved
calls/images/events plus scripts. All five new flights retained; 21 completed flight
calls, five cancelled, one extra completed bbox probe. No cloud, held-out or OnFly edits.
406 unit/contract tests and seven replay/browser cases pass. Next: one bounded
corrected-strategy search validation, not a broad comparison or claimed planning result.

## D-106 — Frozen post-repair capability comparison (2026-09-13)

Status: registered; results pending.
Rationale: close the bounded search validation and compare existing implementations
without indefinite AerialClaw tuning. Eight tasks, three families, seed 1061, 60 s.
Visual-tool profile only covers single-object tasks; other C1 visual task cells
retain explicit text-only/integration-limited status. Privileged C0 and unmatched
latency prevent an architectural ranking. No runtime change in this experiment.
Evidence: reports/frozen_capability_20260913/PLAN.md and FREEZE.json.

D-106 outcome: COMPLETE, 24 frozen flights. C0 6/8 privileged; C1 2/8 raw with
five integration-limited cells; C5 0/8 with arrival/branch/red-visit progress.
Corrected C1 search now validly tested: scan views were not inspected and further
scan is hard-rejected. This supersedes D-105 offline-only search status. C5 visible
arrival reaches 0.335 m; current-image range/stop timing boundary observed, not fixed.
Evidence: reports/frozen_capability_20260913/FINDINGS.md, exact captures and dashboard.
743 completed calls +16 cancellations, zero collisions, 14 C5 constraint violations;
24 manifests match freeze, 19,414 poses match, 72 seeks/24 playbacks/24 close inspections.
No runtime changes, architecture ranking, further flight or active process.

## D-107 — Targeted perception/search and arrival contracts (2026-09-13)

Status: in progress. Rationale: repair measured integration boundaries, then add
explicit ordered-object support. Evidence baseline: D-106 source-aligned captures.
Budget: three single development flights, no adaptive repeats, 60 s, Gemma only.
See reports/targeted_contracts_20260913/PLAN.md. New behavior is opt-in, separately
labeled from historical paper adaptations.

D-107 outcome: bounded work complete, broader search/ordered problems unresolved.
Final C5 arrival-window passes at 13.2 s, 0.371 m with unchanged 2 m criterion and
live validation. Earlier 3 s window failed after response latency; final uses 4 s,
explicitly a temporal-memory variant. Source-only probe limitations corrected by
availability replay. C1 search still repeats detection; ordered prompt fix produces
red detection/goto/dwell, but no transition to blue despite first-complete feedback.
Five flights total after communicated amendment for two concrete implementation
mistakes; all failures retained. No further flight or task active/scheduled.
Evidence: reports/targeted_contracts_20260913/REPORT.md, RUNS.json, exact captures,
SAVED_ONFLY_AVAILABILITY.json and browser verification. Not a reliability ranking.


## D-108 — explicit approach and hover; autonomous debug cycle (2026-09-13)

User replaced ambiguous radius arrival with 1 m approach-side hover, target kept in
view and no touching, and explicitly authorized run/debug/fix without per-run approval.
Retain D-107 unchanged. New scenario: 0.75–1.25 m from marker reference, <=0.35 m
cross-track from initial approach line, <=0.2 m/s, visible for 2 continuous seconds.
The existing marker has no solid body: swept 0.4 m drone-radius exclusion around its
reference implements no-contact scoring; this is not a physical pillar-contact model.
Rationale: distinguish passing/overshooting from stable arrival. Evaluator truth stays
private. Initial run uses unchanged D-107 policy/monitor; diagnose exact captures before
adaptation. Same local Gemma, development seeds only. No automatic unbounded retry.
Evidence: new scenario negative controls; live outcome pending.


D-108 outcome: four retained flights. Final named c5_hover_level_gemma_dev succeeds
11.2 s / 1.0027 m / 2.1 s hover, zero contact/collisions. Intermediate failures expose
old stop semantics, cropped-image identity loss/invalid old-point steering, and a
0.403 m altitude/reference-line mismatch. Repaired with explicit hover validation,
temporal reference/current grounding, grounded waypoint contract and flight-level
endpoint adapter. These are named engineering adaptations, not paper-fidelity or
planning-capability results. Task thresholds/SUPER/controller unchanged. Final raw
speed counter 1 is a 4.44e-16 m/s floating-point excess, retained and separately audited.
Evidence: reports/hover_cycle_20260913/REPORT.md, RUNS.json, VERIFICATION.json,
GROUNDING_AUDIT.json, SPEED_AUDIT.json and full per-flight captures. 433 tests pass;
1,835 replay poses and 12 browser seeks/four playbacks match. No additional run active.


## D-109 — frozen hover repetitions expose unstable completion and yaw (2026-09-14)

Status: two-run validation complete; reliability not established. User explicitly
requested two more flights; no source/config changes across either. Seed1060 passes,
seed1062 times out; same deterministic geometry. Historical-plus-repeats 2/3.
Rationale: test repeatability of D-108 success before expanding tasks. Evidence:
reports/hover_repeat_20260914/REPORT.md, FREEZE.json, VERIFICATION.json,
DEPARTURE_AUDIT.json and full captured calls/images/events/sources.

Failure physically hovers >8 s but monitor rejects completion after a 1.95 s initial
count and later 0.397 m cross-track inferred from a changing body pixel. Residual-goal
controller yaw turns the view away; exact policy obs380 (18.95 s) is sky/ground,
exploration command executes at20 s and causes departure. This is measured
completion/reference/yaw coupling, not evidence of initial route-planning failure.
Next isolate stable camera-facing orientation and temporal/metric hover reference;
retain evaluator thresholds and saved failures. No further flight active/scheduled.


## D-110 - Stable hover reference and heading (2026-09-14)

Status: two bounded flights pass; same-scene validation only.
Rationale: D-109 fails after a physically valid hover. Translation residuals rotate
camera; selecting another body pixel moves the monitor's approach line. Source-time
geometry is combined with return-time dwell. User authorizes autonomous repair.
New opt-in c5_hover_stable_gemma_dev retains a camera approach heading within 0.25 m
of the translation goal, fixes the line to initial odometry and first RGB-D bearing,
counts only intervals with valid endpoints, and resolves monitor completion against
latest observed state after inference. Range, visibility, confirmation, age, speed,
2-second dwell, and task scoring remain unchanged. Old profiles retain old behavior.
This is a named engineering adaptation, not native paper OnFly or a planning result.
Evidence: D-109 DEPARTURE_AUDIT.json. Saved control replay matches all 1,200 poses: at 13.95 s old geometry rejects, fixed
line accepts; at 18 s the new yaw controller corrects toward retained bearing instead
of turning away on 0.000019 m/s translation. This is a component probe, not a flight
counterfactual. 442 unit/contract tests pass; 17 targeted checks rerun after evidence
timestamp metadata correction. New flights: seed1062 passes at15.2 s /1.00198 m /6.1 s hover; seed1060 passes
at13.2 s /1.00179 m /4.1 s hover. No contact/collision. Each raw speed violation
is 4.44e-16 m/s roundoff, retained. 43 completed local Gemma calls +2 cancellations;
zero cloud. All263 frozen hashes hold;1,770 replay poses exact,15 monitor source
images exact,9 browser seeks/3 playbacks and terminal images checked. See
reports/hover_stable_20260914/REPORT.md and VERIFICATION.json. Dashboard port8766
leaves Valley on8765 untouched. Completion remains conservative; first-bearing
accuracy, harder scenes and planning remain open. No third flight scheduled.


## D-111 - Return to clutter navigation after hover repair (2026-09-14)

Status: complete: two failed diagnostic flights; no variant promotion. User authorized proposed
run -> visual diagnosis -> first demonstrated repair -> matched rerun workflow.
Use c5_clutter_stable_gemma_dev, grid_nav_onfly_depth_v2_dev, seed1061,90 seconds.
Environment exactly matches D-98 corrected-depth comparator, including geometry,
pitch,dynamics and success. SUPER,verifier,scheduler,inference settings unchanged.
Transfer grounded VLM waypoint interface,1 m standoff,D-110 yaw hold and4 s confirmed
arrival memory. Calibrated -0.15 pitch. Exclude hover-only line/altitude/dwell contract
and two-image hover prompt: navigation allows detours/vertical motion and asks arrival.
Use generic visual monitor without color guard. This is a named combined integration
variant, not isolated yaw ablation or native OnFly reproduction. Inspect actual model
input,accepted point,planner and movement before attributing outcome. No cloud/key
reads,model changes,clearance tuning,new obstacles or broad sweep. Preserve failures.
Evidence: D-97/98 depth contract,D-107 arrival memory,D-110 hover repair. FREEZE.json
verifies resolved environment and unchanged execution/inference settings.


D-111 first outcome: timeout90 s,closest22.583 m/final37.906 m. Exact images and
prompts confirm wrong target bindings (gray/green versus requested red), before
narrow-passage planning. Existing policy semantic_color_guard uses VLM observed_color
and VLM alternative point, not RGB detector/ground truth. Three saved-frame local
probes remove all three wrong target bindings, but alternatives can still point at
obstacles; no passage-quality claim. Enable only that policy flag in named
c5_clutter_attributes_gemma_dev, preserve baseline and run one matched seed1061.
No runtime edits. This repairs an unchecked attribute contract, not proven navigation.
REPAIR_FREEZE.json records exact configuration. No third full flight scheduled.


D-111 completed: attribute rerun timeout90 s,closest33.343 m/final67.845 m, worse
than first22.583/37.906.89 exploration outputs; contract consistency repair did not
solve subgoal selection/search. No third flight or promotion. Both return-to-clutter
runs diverge before original narrow-gap case.33 targeted tests pass;5,400 displayed
poses exact,178 new policy source images exact,15 seeks/3 playbacks verified. Raw
328/465 violations are solely speed roundoff<=2.22e-16/1.11e-16 m/s.271 completed
Gemma calls total including3 probes,+2 cancellations;zero cloud. User RGB/BGR
hypothesis checked offline through real request construction:224x224 RGB PNG as
Base64,exact bytes preserved,red pixel(205,46,46). Server preprocessing not examined.
Evidence: reports/clutter_stable_20260914/REPORT.md,AUDIT.json,IMAGE_TRANSPORT.json.
Next saved-frame exploration/selected-passage contract, not another full blind run.


## D-112 - Paired saved-frame passage choice and abstention probe (2026-09-14)

Status: complete; no spatial improvement, no promotion or flight. User approved three
saved-frame checks and one focused change. Freeze exact RGB-D at visible red tower
D-98 obs520,hidden target/openings D-111 obs40,and close wall D-111 obs520. Inputs
byte/pixel-match original recordings and saved-control replay. Expectations recorded
before calls; geometry/labels never sent to model. Baseline is D-111 grounded_v1,
without unpromoted attribute flag. Candidate adds a passage-check instruction and
hold response option to remove mandatory waypoint commitment. It is a joint prompt/
action-contract probe, not a prompt-only ablation or implemented flight behavior.
Same model/digest/options/RGB per pair, six calls total with no automatic retries.
Positive target binding, visible free-space choice and abstention evaluated separately.
Use actual unchanged policy lifting for target/exploration replies, then offline
straight-segment clearance. This is not a SUPER feasibility test or proof of no route.
Only consider a flight after improvement; three selected frames cannot establish
reliability. Preserve all replies/expectations and show paired pixels/waypoints.
Evidence: reports/passage_choice_20260914/FREEZE.json. No new inference yet.


D-112 outcome: all six chosen points land on gray obstacle faces. Visible target
pair describes red but returns(499,499), image(111.388,111.388), outside red body
x77..84/y72..97. Candidate changes hidden-target label to exploration but still
selects right wall; close-wall reply does not hold. Existing policy pixel/waypoint
round-trip<=3.18e-14 px. This isolates a selection/grounding failure on these inputs,
not conversion drift or proof of general model incapacity. Six local calls,zero
retries/cloud/flights;1,040 saved poses and3 RGB sources match; six-panel browser
QA/overlay/prompt expansion pass. Probe-only hold not installed. See
reports/passage_choice_20260914/REPORT.md and VERIFICATION.json. Next offline pointing
representation check (box or labeled region versus direct coordinate), not SUPER
margin tuning or a full flight. No further inference scheduled.


## D-113 - Saved-image grid versus bounding-box localization (2026-09-14)

Status: complete; mixed failures, no promotion or flight. User approved comparing labeled
grid selection and bounding boxes on D-112's three exact sources. Grid uses neutral
4x4 labels A1..D4 over224x224 RGB,with absent option. Bbox uses original unmodified
RGB with visible flag and tight [left,top,right,bottom] on0..999; absent box zeros.
Expect B2 on visible red and absent on other two. Box positive requires center in
visible red body and IoU>=0.5 with diagnostic half-open pixel bounds[77,72,85,98].
Freeze expectations before calls; no truth boxes/expected cells sent to model.
Same pinned Gemma/options; no retries/cloud/new flight/runtime edits. These tasks
remove navigation from the prompt and differ in both visual input and output
representation. Coarse cell correctness is not tight localization or a controlled
format-only improvement over D-112. One positive/two negative selected frames are
not reliability evidence. Preserve exact modified inputs and all raw outputs.
Evidence: reports/localization_formats_20260914/FREEZE.json. Grid inspected: labels
and boundaries do not cover red target. No new inference yet.


D-113 outcome: grid selects correct B2 in visible frame but hallucinates C3/B1 on
both absences. Bbox rejects both absences, but visible box[364,333,633,384] has
IoU0.05024 and center outside red body. Case counts1/3 grid,2/3 box reflect different
precision requirements and must not be treated as ranking/reliability. All6 valid
responses/hashed inputs retained; grid leaves red pixels unchanged. Scripts lint,
six-panel browser overlay/prompt QA pass; positive pair inspected. Six local calls,
zero retries/cloud/flights/runtime changes. No format promoted or post-hoc combined
success claimed. See reports/localization_formats_20260914/REPORT.md. Need independent
positive/negative validation before format selection; no further call scheduled.


## D-114 - Installed local VLM localization comparison (2026-09-14, frozen)
User authorizes all seven models listed in the conversation: Qwen3-VL 2B/4B/8B, Qwen3.5 2B/4B, Moondream and SmolVLM2 2.2B. Freeze exact D-113 image bytes/prompts/schemas and scoring before inference, on a separate CPU-only server. No shared-server inference or unload. Full JSON content then thinking parser handles recorded Qwen channel behavior without repairing coordinates. Maximum 42 attempts, no retries; runtime/interface errors distinguished from semantic errors. This is the shared interface on installed backends, not an optimized-native-model comparison or latency benchmark. Gemma is historical; one positive plus two negatives is diagnostic only. Evidence: reports/local_vlm_comparison_20260914/FREEZE.json and seven metadata captures; historical scorer parity verified. Status: prepared; calls pending.

### D-114 outcome - all seven attempted, no runtime promotion
42 durable request records:36 completed replies,6 SmolVLM2 HTTP400 errors because
its installed package lacks multimodal support. Qwen3-VL4B and8B pass grid3/3 and
box3/3. Qwen3-VL2B grid2/3,box3/3. Qwen3.5 2B grid2/3,box2/3;4B grid3/3,box2/3.
SavedGemma grid1/3,box2/3. Visible IoU:QwenVL2B .5946,4B .7765,8B .7145;
Qwen3.5 2B0,4B .0354;Gemma .0502. Moondream grid0/3,three invalidbox outputs.
Scoring used original frozen .5IoU+center gate; precision levels stay separate.
Recommendation:Qwen3-VL4B for an independent image validation,2Bboxes as smaller
candidate. No planning/navigation conclusion from one positive and two negatives.
Shared prompts/schema rather than optimized native model interfaces; packaging,
backend and answer channels are explicit. Qwen3-VL valid JSON is in thinking;
Qwen3.5 in content. All raw channels retained. Requested context8192;Moondream
actual2048 captured. CPU-only latency not comparable to GPU flight execution.
Verification:42 request/image/schema/model identities;36 zero-VRAM residency records;
6 historical scorer regressions,48 browserpanels,overlay/prompt controls;Ruff passes.
Owned11435 server unloaded and stopped;shared11434 remained reachable. No downloads,
cloud,keys read,extra retries,flights or runtime edits. Evidence:reports/local_vlm_comparison_20260914.


## D-115 - New-image Qwen3-VL4B gate (2026-09-15, frozen)
Decision: six new RGB frames, unchanged D-114 bbox interface and installed Qwen4 digest,
separate CPU server at11435. Freeze all-case pass before inference; only if6/6 pass
connect Qwen to current C5 pipeline and run one seed1061 clutter flight.
Rationale: positive D-114 result used one scene. Broaden image positions/scales and
negative views before flight. Two positive frames share a hover run; these are new
images, not six independent environments. Ground-truth references only in evaluation.
Evidence: reports/qwen4_validation_20260915/FREEZE.json and selection.png.
No flight or runtime change yet; no prompt tuning or retries permitted in this gate.

D-115 image result:6/6 pass,3 positiveIoUs .7704/.9383/.9767 and3 correctabsences.
One conditionalflight now enabled: c5_clutter_qwen4_validated_dev,seed1061,
grid_nav_onfly_depth_v2_dev. Resolvedconfig diff verified: only model identities,
digest,host andthinking responsechannel plusprofile name/ID. Point-based prompts
retained;this tests transfer from bbox localization to currentnavigation,not a new
bbox-driven architecture. Fixed simulatedlatency unchanged;actualGPUlatency logged.
48 adapter/OnFly tests pass. Evidence:FLIGHT_FREEZE.json,BROWSER_CHECKS.json.

## D-115 outcome: validated images, unsuccessful clutter flight (2026-09-15)

Decision: retain Qwen4 as a named diagnostic profile; do not promote a general
planning result. Six image checks pass, but the one authorized clutter flight
still times out at 90 s (closest13.75 m versus savedGemma22.58 m), zero collisions.
134 completed flight calls, one final cancellation, no inference errors.
Recovery triggers correctly at37.2 s but expires10.314 degrees short; exploration
resumes while loss remains active. Crucially, a saved-pose offline render at the
complete saved heading still contains no target. Extending the timer alone is
not supported as a sufficient fix. Next isolate reacquisition/expiry semantics
and viewpoint/position recovery; any new search behavior must be named as an
architecture extension rather than silently attributed to the original paper.
Evidence: reports/qwen4_validation_20260915/FLIGHT_REPORT.md, FLIGHT_AUDIT.json,
RECOVERY_COUNTERFACTUAL.json and archived flight/. 1800 poses/89 source images
match; both dashboards replay exactly and pass Edge playback/seeks. 48 existing
adapter/OnFly tests pass. Shared11434 untouched, dedicated11435 unloaded/stopped.
Status: bounded gate + one flight complete; recovery repair remains open.

## D-116 - Autonomous recovery contract cycles (2026-09-15)

Decision: test a fresh-observation handoff as an opt-in repair before adding search.
Rationale: D-115 resumes motion from an image captured while reorienting. Expiry
is not visual reacquisition. Discard pending pre-expiry commands and distinguish
temporal rejection from blocked geometry in the policy feedback. A new post-turn
proposal can still explore; no automatic backtracking or privileged navigation.
Evidence: source obs760 at37.95 s resumes39.25 s; 117 focused tests pass including
legacy/fixed parameterization, delayed reply rejection and fresh resumption.
Status: implementation ready, flight outcome pending. Four-flight total cap and
16:55 UTC deadline in reports/recovery_cycle_20260915/STATE.json.

### D-116 cycle 1 outcome: handoff isolated, target still lost

New run c5_recovery_fresh_20260915_s1061 matches D-115 controls until39.25s.
Fresh-view handoff works: holds,rejects delayed pre-expiry observation at40s,
resumes41s from39.95s image. Timeout90s,closest13.401m vs13.746m,final29.939m
vs29.295m,zero collisions. No navigation improvement or promotion. 134 calls plus
one cancellation. 1800 poses/89 source images exact;20 browser seeks/2 playbacks
pass; actual source strip and41s dashboard visually inspected. Tooling fix excludes
rejection events with no source ID from source-frame lookup. Next offline policy
input/memory diagnosis, not another unchanged flight. One of four slots used.
Evidence: reports/recovery_cycle_20260915/REPORT.md, CYCLE1_HANDOFF.json, cycle1/.
Dedicated11435 unloaded/stopped. Follow-ups active until16:55UTC.

### D-116 continuation: freeze six-call input/action-space diagnosis

Local implementation lock confirms memory belongs to monitoring; policy is current
image plus previous-goal reprojection. Grounded diagnostic prompt omits the latter.
Adding last-seen images or non-point actions is therefore a named extension, not
a repair to the published OnFly mechanism. Freeze two current images (obs800/920)
with last policy-confirmed target obs680, three conditions each: unchanged point
interface, history plus same point interface, history plus diagnostic action choice.
Only onboard odometry, existing model claims and exact saved pixels are supplied.
Six local calls maximum,no retries,no executed movement. Score current visibility
and obstacle-face pointing; inspect action changes, do not claim navigation success
or promote a flight from this probe. See context_probe/FREEZE.json.

### D-116 saved-view probe outcome: context is insufficient with point-only output

Six replies complete without errors. Both current frames absent; all labels agree.
All four point-only answers (with/without history) select gray obstacle faces;
history-point evidence incorrectly names historical red target. Both action-choice
answers distinguish historical/current frames and request backtrack. No action
executed and no general planning claim. Local mechanism lock makes position return
an architecture extension, not an OnFly repair. Next bounded component tests for
VLM-selected return to observed pose+heading before another flight. Reacquisition
is not mission completion; repeated approach-loop risk must remain visible.
Evidence: reports/recovery_cycle_20260915/context_probe/REPORT.md, six frozen
requests/replies, validated current-pixel overlays and browser capture. Dedicated
11435 unloaded/stopped. Flight count remains1/4.

## D-117 - VLM-selected observed-view return extension (2026-09-15)

Decision: introduce a named experimental policy and bound option verifier, not a
silent OnFly modification. Model chooses backtrack/continue/hold; backtrack binds
to its stored observed pose+heading,one request/episode,30s anchor age,20s deadline.
Normal waypoint provenance remains checked; option goals cannot substitute model
coordinates and go through common geometric verification,SUPER,controller.
Optional waypoint camera-heading contract supports pose restoration; stationary
observation holds now have a braking-clearance-checked planner path.
Evidence: saved784-pose prefix followed by stub-selected return restores view in9s,
2.31cm position error,3.13deg yaw error,zero collisions,all10 plans accepted.
Actual RGB shows target reappearing. Return component and unit negative controls
are execution evidence,not a VLM flight result. See return_component/REPORT.md.
Status: component validated; single model flight pending frozen test/commit gate.

D-117 implementation gate:393 unit tests pass (one existing dependency warning),
new tooling/runtime lint passes. CYCLE2_FREEZE.json freezes one Qwen4/1061 flight.
Source-image auditing recognizes historical+current recovery input ordering.

### D-117 cycle 2 outcome: actual return succeeds, repeated occlusion remains

One live Qwen request selects backtrack39s; verified pose+heading return completes
48.5s; actual current RGB target reappears. Decisions50/51s correctly point at red
source pixels. After movement it disappears again and monitor reports LOST53.2s.
Timeout90s,closest14.930m (baseline13.746m),final17.007m (baseline29.295m),zero
collisions,min obstacle distance1.106m. Mixed metrics,not navigation improvement.
124 completed calls+1 cancellation,zero errors.1800 new poses/79 current images/1
historical image exact;32 browser seeks/2 playbacks pass. Actual49s dashboard
and camera sequence inspected. Reports/recovery_cycle_20260915/cycle2/REPORT.md.
Next offline isolate current_grounding's deterministic absence->LOST mapping and
CONTINUE+absence normalization. These conflate occlusion with progress failure;
causal impact needs testing before another flight. Retain strict STOP grounding
and arrival checks. Two of four flights used; dedicated11435 stopped.


## D-118: opt-in semantic progress monitor probe (2026-09-15, provisional)

Code diagnosis: current_grounding discards history, asks only current visibility,
then maps visible to STOP candidate and absence to LOST. A later normalization
also converts CONTINUE+absence to LOST. This prevents temporal progress judgment.
Add semantic_progress=false by default; opted-in monitor receives chronological
history sheet plus separate current RGB and owns its CONTINUE/LOST judgment.
Current target identity, depth, distinct confirmations and arrival-memory checks
remain. Absence+CONTINUE never refreshes last normal recovery anchor.
This is a NAMED semantics ablation, not a claim of native paper fidelity: the
existing paper prompt itself associates disappearance with LOST. No promotion.
Evidence: full unit suite400 passed before additional layout validation; final
test record accompanies commit. Frozen six-call paired probe at obs680/720/1340
from D-115:1340 replay poses,3 actual policy RGB matches, actual monitor request
construction and reconstructed hybrid memory. Independent monitor cases begin
acquired, with no confirmed arrival memory; not a replay of all monitor hidden
state. Freeze contains criteria, exact requests, input hashes, depth and poses.
No cloud, retries or extra flight.


### D-118 outcome: joint semantic/current monitor fails identity gate

Six local calls,all validJSON,zero errors/retries. Legacy current-only passes
current identity3/3 selected scenes; candidate history+current only1/3. At33.95s
its point hits ground;35.95s it transfers HISTORY4/5 target to current gray wall
and asks STOP. Runtime depth/confirmation guards block every STOP in this probe;
false identity still forms a wrong geometric candidate,so do not promote.
401 unit tests pass;1340 replay poses/3 sourceRGB/9 encoded inputs match;6 browser
cards/details and actual point/history images inspected. No new flight;2/4 used.
Read reports/recovery_cycle_20260915/semantic_probe/REPORT.md. Next offline split
current-only grounding from status-only temporal reasoning; the latter must not
redefine visibility/coordinates or authorize STOP. Reuse frozen grounding for
diagnosis only; future live design must charge both calls/latencies. No oracle.
Code/freeze02b3deb; candidate remains disabled/no enabled profile. Dedicated11435
unloaded/stopped.12 saved-frame calls total,shared11434/Valley8765 untouched.


## D-119: status-only temporal monitor probe (2026-09-15, provisional)

Rationale: D-118 joint image-history localization corrupted current identity.
Freeze3 local status-only calls on the same3 source contexts, with the unchanged
D-118 current-only grounding answers supplied as timestamped evidence. Temporal
output is limited to evidence/CONTINUE/LOST; no coordinates, visibility or STOP
authority. No runtime change yet. This is a named architecture experiment, not
paper-profile repair. Gate: valid schema and evidence consistent with current
grounding, CONTINUE visible/first-occlusion and LOST sustained-loss to support a
flight hypothesis. This criterion does not label the route traversable. No repeat
prompt tuning on these cases if it fails. All3 attempts retained, no retries.
Evidence pending in reports/recovery_cycle_20260915/status_probe/FREEZE.json.
Use CPU-only dedicated11435 while Valley runs; do not compare latency to flights.
Frozen grounding reuse is diagnostic; live integration must charge both calls.


### D-119 outcome: current identity respected, first occlusion still LOST

Three status-only CPU calls:CONTINUE/LOST/LOST at33.95/35.95/66.95s; validJSON
and evidence respects frozen current grounding. No experiment-entry gate pass
because first occlusion stillLOST. Six input hashes and CPU residencies verified;
3 dashboard cards/6 details pass. CPU+prompt both differ from D-118,not causal
performance comparison. Keyframe history at35.95 ends27.85,omitting33.95lastvisible;
temporal information may be insufficient. Do not tune these sameframes again.
Next offline execution probe: hold cycle2's last accepted target-bound goal51s
rather than replacing it with52s exploratory wall point; ask if common SUPER
can complete it from saved state. No oracle steering/model call; intermediate
waypoint completion is not mission success. Read status_probe/REPORT.md.
15 saved-frame calls total,2/4 flights; dedicated11435 stopped,Valley untouched.


## D-120: memory-cadence correction and bounded goal-hold fixture (2026-09-15)

Correction: D-118/D-119 prepared history by updating hybrid memory each control
tick; live runtime updates it on decision/perception cycles. Current RGB and raw
responses remain exact,but history is constructed,not exact runtime replay.
Event-ordered audit matches1340 poses and68 memory item counts. Actual history
latest times26.95/34.95/52.95 forcurrent33.95/35.95/66.95: gaps7/1/14s. Thus
the D-119 claim of8.1s live-history gap at35.95 is withdrawn. Preserve raw frozen
inputs/results; no model reruns. Reports/dashboards prominently correct scope.
Evidence: reports/recovery_cycle_20260915/memory_cadence/RESULT.json.

Freeze a separate20s execution component at cycle2 time51s, retaining its already
accepted target-bound intermediate goal. Replay every planner invocation and
control in recorded event order; require prefix pose,plan points/feasibility and
first branch command matches. Repeat common planner1Hz/controller20Hz; no VLM,
monitor or semantic goal replacement. This deliberately renews execution of a
saved goal beyond semantic freshness as a bounded component,not live architecture.
Stop at unchanged1m tolerance,collision or20s. No oracle steering. It tests common
executor capability,not mission success or beneficial commitment policy.
Fixture frozen in goal_hold_component/FREEZE.json; outcome pending.


### D-120 goal-hold outcome: useful detour, intermediate endpoint not reached

Exact1,020 prefix poses/61 planner outputs/first branch command match. Holding
accepted51s target goal for20s produces a collision-free right-side detour; red
reappears by64s in sampled RGB,visible through71s. Evaluation-only true target
distance16.885→10.143m. Frozen waypoint endpoint fails:closest4.928m,final6.150m
(start5.282m),tolerance1m. All20 newplans feasible with known-free backup and
reaches_goal=false.21 UI seeks and actual camera/map inspected. No model calls.
This supports an execution-persistence hypothesis,not mission success or proof
SUPER cannot reach the goal. Intervention removes both replacements and monitor
yaw,so next live extension must make arbitration explicit. Stored goal center
clearance0.423m is below0.6m, but1m tolerance prevents infeasibility conclusion.
Next named bounded target-goal commitment with explicit original-source lease,
fresh-target supersession, expiry, common planning and STOP guards; unit-test
ownership/expiry before one model flight. Do not label as native paper repair.
Evidence: goal_hold_component/REPORT.md,RESULT.json,VISUAL_EVALUATION.json.
Flightcount2/4; saved-framecalls15; shared11434/Valley untouched.


## D-121: bounded accepted-target execution variant (2026-09-15)

Rationale: D-120 held-goal component restores the target after a useful detour,
while live exploration/LOST recovery interrupts the same accepted intention.
Add target_commitment_s=20 only in c5_target_commitment_qwen4_dev. Baselines
default0. An already verified/planned model-target goal arms a candidate. Fresh
exploration or monitorLOST can activate it while original source age<=4s; deadline
is activation+20s and exploration cannot extend it. Replans use fresh onboard
geometry but commands preserve ORIGINAL decision/image timestamp and sourceID.
Deferred exploration is logged rejected,with retained-goal plan metadata. Age
remains measurable; intentional lease commands have their own counter.
Fresh verified target supersedes it. Arrival at the intermediate tolerance ends
the lease without missionSTOP; expiry, STOP or planner failure ends execution.
LOST label is retained andlogged; only its yaw action is deferred while the lease
owns motion. Expiry restores ordinary recovery. Existing STOP guards unchanged.
This is a named architecture extension,not nativeOnFly or D117return-to-view.

Validation: full suite420 passed and20 focused commitment tests passed including
new orchestrator LOST/arbitration integration. Final lint/checks before flight.
Tests cover original-source preservation,nonrenewal,expiry,staleness,reset,
verified supersession,rejected-target retention,planning failure,recovery ownership
and defaultoff behavior. Policy feedback says deferred,not obstacle-rejected.
One flight frozen in CYCLE3_FREEZE.json. CPU-only dedicated11435 while Valley runs;
hardware placement differs from priorGPUflights, so inspect pre-lease equality and
do not treat outcomes as a clean architecture-only comparison if prefixes differ.
No cloud/newmodelcalls/reinstalls; fixed simulated latencies unchanged. Third of
four flight slots reserved,2 completed; deadline16:55UTC.


### D-121 debugger provenance support

Retained-goal replans are logged under rejected incoming exploration but command
source remains the original accepted target. The debugger now chooses the latest
feasible plan atcursor time by its explicit execution owner,not the original
decision's first plan. This prevents displaying a stale path during a commitment.
Five browser behavior checks cover old/new/infeasible/future/unowned plans.
Runtime flight3 remains unchanged andrunning; this is offline viewer support.


### D-121 flight audit preparation

Dedicated11435 residency confirms Qwen3-VL4B entirely onCPU(size_vram0); shared
ValleyGPU untouched. Added completed-flight audit for original target sourceID/age,
nonrenewing20s deadlines, deferred exploration versus executed commands, LOST
label/action arbitration and realized control-prefix comparison against D115/D116.
Browser review will seek each actual lease activation,midpoint anddeadline.
No flight restart or runtime changes; cycle3 continues.
