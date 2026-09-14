# TODO

Open work, ordered by what it blocks. Every item names the decision it comes
from (`D-nn` in [`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md)) and the first
concrete step, so nothing here needs re-deriving before it can be picked up.

Kept separate from the research log on purpose: the log records what was
*decided*, this records what is *undone*. An item leaves this file when it
becomes a decision with evidence.

---

## D-107: remaining tool-choice and ordered-state diagnosis

C5 stationary arrival window now has one successful flight; retain as a named
variant, not a global paper-profile replacement. Search still repeats detection;
ordered task now completes red but does not transition to blue. Inspect exact saved
prompts at 26.2 / 34.7 / 43.2 s: first completed is true, but per-label context still
names the last queried red object. Audit consistent task-state/tool contracts before
another flight or model-quality conclusion. The five-flight bounded run is complete.
See `reports/targeted_contracts_20260913/REPORT.md` and retained failed variants.

## D-106: use the frozen failure map before further changes

24-cell comparison is complete; read `reports/frozen_capability_20260913/FINDINGS.md`.
First isolated contract checks: C1 scan/retry gating vs actually inspected views;
C5 arrival range, source timing and target-view loss. Five C1 visual tasks need
explicit capability integration before interpreting their model performance.
Choose one check, preserve the frozen baseline, and separate a contract repair
from a new architecture variant. No additional flight or broad sweep is scheduled.

## D-103: task suite ready for subsequent architecture evaluation

Eight first scenarios are implemented and physically validated with scripted
fixtures, plus one C0/SUPER integration. Read `docs/CAPABILITY_SCENARIOS.md`.
Future model trials should start one task at a time with exact dashboard capture;
no trial is scheduled. Do not infer that C1/C5/MapGPT solve these tasks, and do not
restore labeled semantic_hits just to recover historical scores. The remaining
16 proposed scenarios are not implemented. VLA training remains separate.

## D-102: resolve gate/planner disagreement, then test rejected-goal recovery

D-101 real Gemma preflight and first 90 s flight are complete. Read
`reports/adaptive_plan_flights_20260912/REPORT.md`. Use the exact saved 19 s and
32 s cases to test a targeted acceptance-contract correction: the gate rejects
both while copied historical SUPER produces full known-free paths to both goals.
This is not yet physical execution proof. Preserve schema/geofence/staleness checks
and shared planner constraints. Separately represent rejected versus accepted goal
state before evaluating retain/replan behavior; feedback already reaches the VLM.
No runtime fix or further run scheduled. Do not change both mechanisms at once or
claim that this one component adaptation establishes general VLM planning ability.

## D-100: deferred graph-candidate direction (superseded by D-101)

Source audit and matched comparison are defined in
`docs/research/drone_control_graph_comparison_20260912/REPORT.md`.
First implement typed candidate snapshots with stable IDs and an observation-derived
map adapter, then display candidates, viewing directions, route evidence and
visited/failed state in the flight debugger using saved observations. Validate the
geometry/identity contracts offline before adding Gemma selection. Shared target
grounding is a separate unresolved preflight gate. Preserve the current C5 and SUPER;
no additional flights or inference sweep is scheduled. A later graph/classical versus
graph/Gemma comparison changes only the selector, with latency cost reported.

## D-95: inspect the planner's geometry at the tested passage

The manual physical probe is complete: the opening can be crossed from the
selected dynamic state with an 8.04-degree aiming change, but the successful
route's 0.613 m center-to-wall separation is below the 1.8 m planner clearance
parameter. Next inspect inferred occupancy, inflated cells and committed route
at that state. No runtime margin change, model call or sweep is scheduled.
Evidence: `reports/passage_probe_20260912/REPORT.md`.

## D-94: inspect one shared decision before choosing the next experiment

The flight debugger is ready: `reports/debugger/index.html` and
`docs/FLIGHT_DEBUGGER.md`. First select a failure moment and record expected
versus observed behavior with its run/time/decision ID. Distinguish source image,
model proposal, routing and actual control before proposing a causal test.
No more model calls or navigation runs are scheduled. Future authorized runs
should enable exact diagnostic capture; old missing raw evidence stays missing.

## D-93: positive grounding before more navigation tuning

The five-flight autonomous debugging budget is complete. None passed; leave
the active profile unchanged. First establish positive/negative saved-image
grounding, including actual target pixels and distractors. The model describes
a red rectangle but rejects the target in the positive control. Review D-92
source-aligned scoring and D-93 report before interpreting previous metrics.
No further flights are scheduled. Preserve task, quota and held-out restrictions.

## The headline

**AerialClaw/C1 is now the first accepted real foundation-model architecture;
the other paper families are not yet model-valid.**

The accepted C1 uses real local `gpt-oss:20b` inference and passed 5/5 grid plus
5/5 object-search development episodes with explicit typed stops and zero
collisions. `mock_vla`, `vlm_waypoint` and `chunk_vla` remain scripts; the
learned direct policy does not navigate, and no Gemma VLM configuration
completes a mission. Results outside frozen SUPER and AerialClaw therefore
remain harness or negative-capability results, not evidence for the remaining
paper families.

So what the testbed currently demonstrates is that **the harness works**: it
composes architectures from configuration, charges model latency to a simulated
clock, separates them on measurement, and catches its own defects. It does not
yet demonstrate anything about foundation-model autonomy. That gap is items 1
and 2 below and nothing else should be presented as a result until they close.

## Current local-simulator work order

- [x] Implement and freeze the SUPER-derived shared execution substrate before
  touching the seven semantic systems (D-43). Acceptance is defined in
  `docs/fidelity/SUPER.md`; the frozen gate passed 40/40 with zero collisions
  and zero shield interventions.
- [ ] Implement paper-faithful systems one at a time. **AerialClaw is accepted
  and frozen; native SPF is externally blocked; AeroVLA's mechanism is
  integrated but its Gemma profile is rejected. C5 OnFly's Qwen3-VL 4B
  native-dynamics profile now has its first clean end-to-end success: seed 1061
  reached 0.65 m, stopped correctly, made one bounded recovery, and had zero
  collisions or parse errors. Seed 1060 still fails because the requested red
  target is never visible in any of 89 decision frames; that is a missing
  semantic-search capability, not a monitor/runtime fault.** The five-seed gate
  remains open and C5 is not accepted yet. Exact evidence is in
  `reports/paper_implementation/ONFLY_QWEN4_RECOVERY_FIX_20260901.md` (D-52).
  Do not hide the remaining search boundary with color detection, simulator
  truth, scripted target search, or a weaker SUPER substrate.

- [x] Correct the design space to **one classical baseline plus five autonomy
  families**. Fast/slow reasoning is a named subfamily of `hybrid_stack`, not a
  seventh peer family (D-41).
- [x] Freeze the first top-level local-simulator screen as C0, C1, C2, C3, C6
  and C8 in `configs/experiments/core_families_local.yaml`.
- [x] Label validity explicitly: C0 is the only privileged oracle; scripted
  C1/C2/C8 slots test architecture wiring, not foundation-model performance.
- [ ] Replace the unreliable real-VLM grounder, then rerun C2/C2G/C3G/C6G on
  held-out local-simulator seeds. RGB-D terminal range is now available and
  safely verified, but Gemma still has zero capability (item 2, D-42).
- [ ] Replace failed behaviour cloning with a recurrent/on-policy direct-action
  learner and keep seeds 1–40 held out (item 1).
- [ ] Run the six primary representatives across the remaining local regimes,
  then evaluate ablations. Do not move to AirSim or Gazebo before the real-model
  gates pass.

---

## Blocking the central claim

### 1. Make a learned policy actually fly — D-27
The direct-VLA family has no working learned member, so the family's whole
premise is untested.
**State.** Three interventions, each fixing its measured defect, none the
binding constraint: teacher swap (C0→C2), DAgger, dilated frame stack.
Reached-goal stayed at 0.03–0.05 throughout. The full post-D-14 rerun is now
done (D-39): 98/250 successful teacher flights, 22,025 samples, 1.439 m/s held-
out velocity error. C7T still scored 0/40; C8T scored 0/40 and entered the goal
radius once. The search defect was not the binding constraint.
**First step.** Stop repeating behaviour cloning. Train an on-policy recurrent
direct-action policy in the local simulator, or change the teacher interface so
the label is a function of the student's observation. Keep seeds 1–40 held out.

### 2. Get a real visual model to complete a mission — D-27
A real LLM now completes C1 missions, but Gemma 3 4B runs, parses, and grounds
at 0.93 detection accuracy while no `g`
configuration has ever finished a mission.
**State.** Corrected post-D-14 screen on held-out seeds 1–3: C2 2/3, C2G 0/3,
C3G 0/3, all Gemma failures timeouts (D-40). A standalone C2G seed-2 run did
enter the goal radius at 52.35 s with 14/22 grounded frames and no parse errors,
but Gemma never reported arrival and the vehicle left again. Prompting for
target scale caused a premature stop 27.6 m away and was reverted. Qwen3-VL 2B,
Moondream and SmolVLM also failed the structured grounding/arrival contract.
**State after D-42.** Calibrated RGB-D range now sits behind the VLM pixel, with
world-coordinate consistency and a second cropped VLM check before stop. The
unsafe variants were rejected: triangulated steering ended 50.5 m away, active
parallax ended 36.7 m away, and depth-only stopping stopped 24.8/27.7 m away.
The safe three-seed gate produced no premature stops but still scored C2G/C3G/
C6G 0/3. With the fair 90 s horizon, C2G seed 2 entered the goal at 62.65 s but
crossed it between calls and never reacquired it for a valid stop. Qwen3-VL 2B
still emits only `thinking` even with Ollama `think:false`.
**SPF paper-profile update (development seeds only).** The clean-room C2 profile
now reproduces SPF's RGB-only `(u,v,distance)` schema, nonlinear travel map and
camera lift without the old RGB-D arrival mechanism. Gemma 3 4B returned the
wrong top-left point; Qwen3-VL 2B had non-monotonic labels; Gemma 4 always used
label 5. Qwen3-VL 8B grounded and entered the target region once but crossed it
without the required repeated near-label stop. Prompt/termination variants
either stopped 4.1-4.8 m early or lost the target and were reverted. Gemma 3
12B improved pointing but produced non-monotonic labels `6,4,4,3,4,3` and no
near label at 1.5-2 m. Seeds 1-40 remain untouched.
**OnFly paper-profile update (development seeds only).** C5-OnFly-Gemma-3-4B
timed out on seeds 1060/1061 with zero collisions and no parse errors. Exact
command replay found the red target in 0/33 and 6/33 decision frames; Gemma's
median error on the six visible frames was 42.83 px. Qwen3-VL 8B localized five
of those six frames when interpreted as normalized 0--100 coordinates, while
the current adapter interprets the same values as raw 224-pixel coordinates.
The scheduler also achieves 0.370 Hz rather than its declared 2 Hz, and accepted
trajectories continue past the 8 s staleness limit. Full analysis:
`reports/paper_implementation/ONFLY_FAILURE_ANALYSIS.md`.
**First step.** The minimum external requirement is access to the paper's
Gemini-class VLM (or a
released open checkpoint that passes the locked SPF point/range probe); do not
add depth, target-size scripts, privileged stopping, or weaken the gate.

### 3. Say so, everywhere
The scripted-stand-in caveat has been stated only as a closing remark and did
not land.
**Done** — the headline is now the first thing in `README.md`, in
`docs/RESEARCH_LOG.md`, and at the top of this file.

---

## Blocking interpretation of existing results

### 4. Make C11 a clean ablation — D-31
C11 changes the action horizon *and* the policy implementation, so "what does
chunking cost?" has no answer. The measured 0.25 drop from C10 splits roughly
0.15 policy / 0.11 horizon and neither is trustworthy.
**First step.** Give `chunk_vla` and `mock_vla` one shared action law with the
horizon as the only difference.

### 5. Explain the C11 gap — D-33
Rejected already: memory swap, in-chunk velocity decay, cruise speed, every
chunk length 1–8, and stopping (zero arrived-but-never-stopped across all four).
C11 reaches the goal 23/40 against C8's 37/40.
**First step.** Blocked on item 4 — a confounded ablation cannot be explained.

### 6. Fix the chunked policy's yaw properly — D-32
`chunk_vla` never turns. Giving it `mock_vla`'s yaw law took C11 to **0.00**,
because a rate held open-loop for 0.8 s over-rotates.
**First step.** Integrate heading error across the chunk instead of holding a
rate.

### 7. Quantify the depth guess — D-17
The waypoint is placed at a fixed hop along the ray because a monocular pixel
carries no range. Unquantified, and it sits under every waypoint-family result.
**First step.** Log unprojected range against ground-truth range per decision.

### 8. Re-measure everything that predates D-14 — D-15
The search could not travel. Affected: the occlusion finding, the boustrophedon
sweep (D-11), `search_altitude_m` (D-13), and C3-versus-C6 being identical on
18 of 20 seeds.
**First step.** Re-run each comparison; they are all cheap.

---

## Coverage gaps

### 9. Only `grid_nav` has been baselined
Four of five regimes have no post-D-14 numbers at all.
**First step.** Score the six primary representatives on `object_search`, `failure_recovery`,
`fine_maneuver` and `occlusion`.

### 10. `object_search` and `failure_recovery` were unusable
Six architectures scored 0.00 on the former; all non-oracle scored 0.00–0.12 on
the latter. Both predate D-14.
**First step.** Item 9 will say whether they still are.

### 11. No ablation has been scored since the restructure
Fifteen of the twenty-two configurations have no current numbers.
**First step.** Follows from items 4 and 9 — bases first.

### 12. Strengthen the verification gate — D-28
`uavlab verify` checks a component *fires*, not that it *influences*. C4G and
C5G passed while behaviourally identical to C3G.
**First step.** Compare against the same architecture with the component
removed and require the trajectory to differ.

---

## Before the AirSim benchmark

Prerequisites, not nice-to-haves. Each is a thing the port would otherwise
discover the expensive way.

### 13. A real visual model must be capable first — blocks everything below
AerialClaw now proves a real LLM can operate through the runtime, but AirSim's
contribution is photorealistic imagery and C1 reads normalized semantic
detections rather than pixels. Porting the remaining scripted/failed visual
members buys cost without visual evidence. **AirSim is only meaningful once a
VLM or direct visual policy passes its local capability gate.**

### 14. Runtime boundary — verified clean ✅
`core/` and `plugins/` contain no reference to any concrete environment, so the
episode path really is simulator-agnostic. Pinned by
`test_the_runtime_never_reaches_for_a_concrete_environment`.

One leak was found and fixed while writing that test: the point-and-fly policy
imported `Camera` from the toy simulator's rendering module to do its own
geometry, which would have made it unrunnable on any other simulator. `Camera`
now lives in `core/camera.py`; adapters supply intrinsics, policies unproject.

### 15. The tooling is *not* portable
Data collection, DAgger rollouts and video capture all monkeypatch
`DeterministicEnv.step`. None of them runs on another simulator as written, so
on AirSim there would be **no training data, no DAgger and no video** — the
three things most needed when a port misbehaves. Pinned by
`test_the_tools_that_do_bind_to_one_environment_are_the_known_ones`.
**First step.** Give the environment interface a recording hook, so the tools
subscribe rather than patch.

### 16. Determinism has no story under AirSim
Every comparison here is paired-by-seed, and that rests on episodes being
reproducible. AirSim is a real-time engine with physics and rendering that are
not bit-reproducible across runs. The method may not survive the move.
**First step.** Run one AirSim configuration twice on the same seed and measure
the divergence *before* designing any experiment around it. If it diverges, the
statistics change from paired to unpaired and every sweep needs more episodes.

### 17. The compute budget does not carry over
The current design is 22 configurations × 40 seeds × 5 regimes. At toy-sim
speeds that is minutes; at AirSim speeds it is not feasible.
**First step.** Decide the reduced design — probably six representatives, one regime,
fewer seeds — and state it before running, so it is not chosen after seeing
results.

### 18. Nothing has been checked against a scene the harness did not generate
Scenes here are generated by the same code that scores them. An adapter for an
authored AirSim environment has to supply goals, obstacles and success criteria
from outside.
**First step.** Define what an adapter must provide, using
`dataset_replay/replay.py` as the existing worked example.

---

## Deferred, deliberately

- **C0 is no longer a ceiling.** At 0.88 it sits below C2, C3 and C6 and fails
  on collisions rather than semantics. Either fix its flight or stop calling it
  a control ceiling.
- **PX4/Gazebo and Project AirSim adapters are stubs.** Nothing depends on them.
- **`mypy`** is wired into CI but has not been run locally. Focused `ruff`
  checks now pass for the C3/Qwen-VLA changes.
- **OpenVLA-7B** for the AerialVLA LoRA: 17 GB VRAM at bf16, ruled out on this
  hardware; revisit only at 4-bit.
### Paper-faithful architecture continuation (2026-08-25)

- [x] Integrate AeroVLA's dual-view, coarse-bearing, 99-bin direct-action
  mechanism as clean C7/C8 testbed profiles.
- [x] Reject the Gemma AeroVLA profile after three real local-sim iterations:
  the final run emitted neutral `(49,49,49)` on all 19 calls. Do not add a
  scripted fallback.
- [ ] Run native AeroVLA only when the official OpenVLA-7B base and sufficient
  VRAM are available; current 8 GB hardware is below the paper's 17 GB report.
- [x] Lock OnFly from the paper and map it to C3/C4/C5 rather than adding a new
  family or a private runtime.
- [x] Implement OnFly decision, visual monitor, recent/hybrid visual memories,
  semantic-geometric verifier profile, configs, and focused tests.
- [x] Close the C5 OnFly Gemma development gate after seeds 1060 and 1061 both
  timed out safely. Two failures make the locked 4/5 criterion impossible;
  seeds 1062-1064 and held-out seeds 1-40 were not consumed.
- [x] Reopen OnFly with the installed shared Ollama `qwen3-vl:4b` checkpoint
  (Q4_K_M compatible backend, not AWQ). Fix the 4096-token monitor rejection,
  latest/history ambiguity, and repeated LOST-recovery loop. Seed 1061 now
  passes end to end.
- [x] Complete the C5 development decision on seeds 1060–1064 under
  `grid_nav_onfly_native_dynamics`. The retained result is 1/5 success, zero
  collisions, and zero inference/parse errors. Seeds 1060/1062/1063 never
  observe the target; seed 1064 sees it initially and loses tracking. Freeze
  this as a capability failure rather than adding hidden target-specific
  steering. See
  `reports/paper_implementation/C5_RETAINED_FIVE_SEED_RESULTS_20260901.md`.
- [ ] Finish PMR as C6 inside the shared testbed. The fixed 18D learned-CVI
  contract, guards, observable admission log, two-model inference routing, and
  real typed GPT-OSS recovery-skill reasoner are implemented. Its repeated
  three-case static gate passes exactly; the rule-only C6 remains an ablation.
  Next collect paired K=5 invocation-versus-local utility labels on seeds
  2000-2015, fit/freeze the linear checkpoint on 2040-2047, and only then run
  development seeds 1060-1064. Held-out seeds 1-40 remain untouched.

### C3 boundary and Qwen-VLA training (2026-08-31)

- [x] Preserve C3 as the OnFly decision + semantic/geometric verifier
  ablation. Do not add monitoring or memory to C3; those mechanisms define C4
  and C5.
- [x] Use `c5_onfly_qwen4_shared` as the full OnFly representative in the
  professor end-map experiment. Its real Qwen monitor was observed updating
  hybrid memory and returning `CONTINUE`; focused tests cover the STOP path.
- [x] Add a C0-labelled Qwen3-VL action dataset collector with exact
  train/deployment prompt sharing, dual-view mosaics, 99-bin AeroVLA actions,
  held-out seed protection, and whole-seed train/validation splits.
- [x] Add official-Qwen and native-ms-swift JSONL outputs plus a validator for
  leakage, missing images, malformed targets, split overlap, and LAND coverage.
- [x] Add the executable QLoRA-SFT recipe and evidence-backed training plan in
  `scripts/train_qwen_vla_sft.ps1` and
  `docs/research/QWEN_VLA_TRAINING_PLAN.md`.
- [ ] Free or move at least 15-20 GB, install ms-swift/bitsandbytes in a
  training environment, collect >=100 successful episodes / >=10,000 samples,
  and run QLoRA SFT. The current AWQ checkpoint remains the inference model,
  not the default training base.
- [ ] Evaluate the SFT adapter on development seeds 1060-1064. If it fails on
  student-induced states, add C0 labels there and repeat SFT for 2-3 DAgger
  rounds. Consider GRPO only after the policy reaches at least 3/5.

## D-105 follow-up: requested-perception search
- Completed in D-106: corrected search flight timed out; scan/perception gate conflict documented. The prior invalid-setup run remains preserved.
- Inspect detect_object requests after scan, coverage selection and completion before changing prompts again. Preserve 60 s horizon and model/latency provenance unless explicitly comparing a new condition.
- Multi-object ordering and dynamic tracking require task-specific completion evidence; do not claim the current single-object visual tool solves those categories.


## D-108 remaining limits after verified approach hover

- Do not rerun unchanged approach fixture. Extend geometry only as an explicit next
  validation, then examine generalization; one deterministic case is not reliability.
- Exact two-image requests are authoritative; inherited current_grounding identifiers
  should eventually distinguish reference/current hover grounding in diagnostic labels.
- Historical speed violation rounding should be addressed separately with explicit
  numerical tolerance tests; preserve old results and physics/replay compatibility.
- Return to the saved AerialClaw ordered prompt-context audit and search tool-selection
  boundary when resuming broader task suite. Neither is solved by D-108.


## D-110: limits after hover repair

D-109 immediate repair completed with saved-state checks and two passing flights.
Preserve both old failure and new named variant. See hover_stable_20260914/REPORT.md.
Next hover validation should change geometry explicitly, testing estimated approach
bearing and target-reference accuracy; another identical scene is not generalization.
Completion still waits beyond two physical seconds because evidence renewals and
monitor cadence are conservative. Do not relax scoring to make the stop earlier.
Broader VLM planning and AerialClaw ordered/search issues above remain separate.
No further flight is active or scheduled.
