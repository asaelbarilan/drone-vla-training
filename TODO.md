# TODO

Open work, ordered by what it blocks. Every item names the decision it comes
from (`D-nn` in [`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md)) and the first
concrete step, so nothing here needs re-deriving before it can be picked up.

Kept separate from the research log on purpose: the log records what was
*decided*, this records what is *undone*. An item leaves this file when it
becomes a decision with evidence.

---

## The headline

**Every architecture number in this repository is produced by a hand-written
scripted policy, not by a learned or foundation model.**

`mock_vla`, `vlm_waypoint`, `scripted_skill`, `chunk_vla` are all scripts. The
one learned network that exists — `learned_visuomotor`, 427k parameters, in
`c7t`/`c8t` — does not navigate (0.03 success). The Gemma 3 4B configurations
run real inference but no Gemma configuration completes a mission.

So what the testbed currently demonstrates is that **the harness works**: it
composes architectures from configuration, charges model latency to a simulated
clock, separates them on measurement, and catches its own defects. It does not
yet demonstrate anything about foundation-model autonomy. That gap is items 1
and 2 below and nothing else should be presented as a result until they close.

---

## Blocking the central claim

### 1. Make a learned policy actually fly — D-27
The direct-VLA family has no working learned member, so the family's whole
premise is untested.
**State.** Three interventions, each fixing its measured defect, none the
binding constraint: teacher swap (C0→C2), DAgger, dilated frame stack.
Reached-goal stayed at 0.03–0.05 throughout.
**First step.** Re-run the whole pipeline now that D-14 is fixed. Every dataset
was collected from a teacher whose search could not travel more than 21.5 m from
launch, so the training data itself was degenerate. This is the single most
likely explanation and it has not been tested.

### 2. Get a real model to complete a mission — D-27
Gemma 3 4B runs, parses, and grounds at 0.93 detection accuracy, but no `g`
configuration has ever finished a mission.
**First step.** Re-score `c2g` on 20 seeds post-D-14, paired against `c2`. The
scripted and real variants share the search that was broken, so this may have
moved on its own.

### 3. Say so, everywhere
The scripted-stand-in caveat has been stated only as a closing remark and did
not land.
**First step.** Put the headline above at the top of `README.md` and
`docs/RESEARCH_LOG.md`.

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
**First step.** Score the seven bases on `object_search`, `failure_recovery`,
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

## Deferred, deliberately

- **C0 is no longer a ceiling.** At 0.88 it sits below C2, C3 and C6 and fails
  on collisions rather than semantics. Either fix its flight or stop calling it
  a control ceiling.
- **PX4/Gazebo and Project AirSim adapters are stubs.** Nothing depends on them.
- **`ruff` and `mypy`** are wired into CI but have never been run locally.
- **OpenVLA-7B** for the AerialVLA LoRA: 17 GB VRAM at bf16, ruled out on this
  hardware; revisit only at 4-bit.
