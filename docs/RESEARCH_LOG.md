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
