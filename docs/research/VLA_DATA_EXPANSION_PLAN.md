# VLA data expansion plan — D-127

The user requires a VLA for the paper, other simulators and eventual real flight.
The current red-tower corpus is a pipeline fixture only. Its percentage of the
required data is unknown; neither 4,765 frames nor any fixed byte count measures
task or domain coverage. A successful local overfit does not complete this plan.

## Required stages and deliverables

| Stage | Data and deliverable | Gate before advancing |
|---|---|---|
| 0. Correct local supervision | Small newly recorded episodes with synchronized original RGB, instruction, odometry, raw teacher commands, decoded commands, executed controls, pose trajectory and terminal evidence | Frame/unit/timing checks, bounded quantization error, explicit clipping report, distinct hold/stop, full debugger trace; no privileged answers in student inputs |
| 1. Diverse paper tasks | New training scenes covering the eight regimes below, with multiple instructions and meaningful behavioral alternatives | Category-level coverage report; freeze new validation scenes and instruction families before tuning; audit teacher quality and what is observable to the student |
| 2. Other simulation domains | At least one additional photorealistic simulator source, different scenes, camera/lighting/appearance and dynamics | Inspect a small episode sample, validate its native action/sensor contract and record adaptation losses; implement/test the second simulator's execution adapter |
| 3. Real-flight recordings | Licensed recorded real UAV data, with calibrated cameras and time-aligned state/control where available; later target-platform recordings to address measured gaps | Establish whether actions are commanded or inferred; validate units/frames/calibration, control cadence, interventions and terminal semantics; reserve unseen sites/flights |
| 4. Mixed-domain training | Source-balanced batches and progressive episode-count increases using audited sources from stages 1-3 | Per-task and per-domain learning curves; compare sim-only with mixed-data training at declared budgets; prevent the largest source from overwhelming the rest |
| 5. Transfer evaluation | Frozen checkpoint in the paper simulator, an independent simulator and real-flight offline replay/shadow control | Report each domain separately, including failures and onboard latency; offline success alone does not establish safe physical deployment |

Stages 2 and 3 are required parts of the broader project, not optional work
that disappears if the local pipeline succeeds. Actual physical flight needs
the target aircraft/controller interface and a separately bounded flight plan.
Continue stages incrementally; do not download all corpora or start long training
before schema samples and resource budgets are checked.

## Paper-aligned task coverage

Use the existing eight categories without changing architecture baselines.
Training scenes must differ from the small development fixtures.

| Regime | Needed demonstrations and contrasts |
|---|---|
| Known-goal navigation | Different public goal coordinates, headings, altitudes, obstacle routes and explicit completion |
| Semantic goal navigation | Multiple object identities/attributes, distractors, visibility and start positions; different instructions on otherwise matched observations |
| Semantic search | Initially unseen targets, multiple bearings, occlusion, target absent cases and reacquisition; no truth-derived target bearing |
| State reasoning | Visually distinct states with matched distractors; choosing the correct state must change the action |
| Conditional tasks | Both branches of each condition, e.g. open/blocked routes; do not encode the answer in student metadata |
| Multi-stage missions | Different target orders and instructions; record history/progress available to the declared policy, intermediate holds versus final stop |
| Recovery | Blocked routes, off-nominal starts, loss/reacquisition and disturbances; record interventions separately from autonomous actions |
| Continuous visuomotor control | Moving targets, varying speeds, turning, vertical motion, tracking, braking, hover and sustained control |

A reactive single frame may not identify progress in a multi-stage mission.
Freeze any added history/proprioception/subgoal interface as a named adaptation
and apply the same executor contract across matched architecture comparisons.
Do not silently add task answers or replace the architecture's reasoning with
a training-data shortcut.

## Source shortlist and admission

Previously inventoried candidates include UAV-Flow, UAV-Flow-Sim, TravelUAV and
Exp2VLA. Their names in this plan do not mean they are already imported, licensed
for every intended use, or action-compatible. Revalidate source revisions and
licenses when importing; use the existing inventory to choose small samples.

For each candidate, first inspect a small set of complete episodes (target
5-10 if selectively accessible; otherwise inspect the smallest available shard
and measure its disk requirements). Record:

- Source URL/revision, data/weight license, checksums, original split, scene/site,
  episode ID, simulator or real origin, airframe and teacher.
- Instructions and task category; cameras actually present, intrinsic/extrinsic
  calibration, timestamps, frame rate and image quality.
- Coordinate convention, units, command versus achieved motion, angular
  representation, control frequency, action horizon and original controller.
- Terminal meaning, failure/intervention flags and any privileged fields.
- Source-to-training adapter, missing modalities, conversion error and rejected
  records. Never fabricate a downward camera or silently substitute pose
  differences for commanded velocity.
- Downloaded, extracted and cached bytes; deduplicated episode counts and hours.

Keep incompatible discrete navigation, waypoint, velocity and low-level control
sources separate until a defensible adapter exists. A source may be useful for
visual/language representation learning without being valid action supervision.
Real-video availability alone does not supply the action labels needed for BC.

## Split and adequacy rules

- Preserve existing datasets, 80/20 seed assignments and baseline profiles.
- Never use seeds 1-40 for development; exclude 1060-1064 from this pilot's training.
- Preserve external benchmark test splits. New group splits must separate sites,
  scenes and episodes; check duplicates across corpora before allocating splits.
- Hold out instruction templates/compositions where language transfer is claimed.
- Reserve real sites and a simulator/domain for transfer evaluation, with a
  development subset separate from final evaluation.
- Track independent episodes, flight hours, scene/site counts, unique instructions,
  action balance, terminal positives and interventions, not adjacent frames alone.
- Freeze a coverage manifest and per-regime criteria before each training stage.
  Use progressive data scales and validation learning curves to decide whether
  another data source, more episodes or a model change addresses the failures.
- Evaluate image/instruction perturbations and simple constant-action controls
  to detect shortcuts. Record success, collisions, false stops, hold/stop errors,
  control tracking error and inference latency by task and domain.

## Immediate sequence

1. Finish and validate the additive control contract; audit its execution through
   the shared controller, rather than accepting a codec round-trip alone.
2. Recollect a tiny local set with raw controls, poses and terminal evidence and
   show it in the flight debugger. Retain all original data and failures.
3. Audit small external-simulator and real-flight source samples into a coverage
   manifest; resolve missing control labels/calibration before large downloads.
4. Run the tiny overfit, then a bounded local pilot on certified labels. Test the
   actual chosen pretrained backbone separately from any surrogate pipeline model.
5. Expand into stages 1-4 above. Before paid compute, present the exact machine,
   measured throughput, storage retention and maximum spend for approval.

No external source has been added by this planning change. No trained checkpoint
or transfer capability is claimed.
