# uav_arch_lab

A modular testbed for searching single-UAV foundation-model autonomy architectures.

The organising principle is one sentence:

> **Architectures are configuration; simulators, models, controllers and datasets are adapters.**

This is not an implementation of any one paper. It is a runtime in which
skill-agent, VLM-waypoint, direct-VLA, dual-loop, hierarchical and
selective-recovery systems are **configurations of one codebase** rather than
separate codebases — so that a comparison between them measures architecture
instead of implementation effort.

## Quick start

No CUDA, no ROS, no Gazebo, no network, no model downloads.

```bash
pip install -e ".[dev]"
```

Run one episode:

```bash
uavlab run --arch c3 --env grid_nav --seed 7
```

Run a staged experiment:

```bash
uavlab sweep --experiment safety_screen
```

See what exists:

```bash
uavlab list
```

Check that every architecture is legal before launching anything:

```bash
uavlab validate-config
```

## What "architectures are configuration" means here

`c3_verifier.yaml` in full:

```yaml
_base_: [c2_vlm_waypoint.yaml]
id: c3
verifier:
  name: semantic_geometric
```

That is the entire difference between C2 and C3. The same is true throughout:
C8 is C7 plus a shield, C12 is C11 with `scheduler.kind` changed from `periodic`
to `async_multi_rate`. Because the configs inherit, it is *mechanically* true
that C7 and C8 use the same policy — which is what the contrast needs in order
to mean anything.

## The five things being varied

| Axis | Values | The question it answers |
|---|---|---|
| Foundation-model authority | `skill` / `waypoint` / `direct_vla` | Where does learned semantic intelligence hand off physical authority? |
| Reasoning schedule | periodic / coupled / async multi-rate / event-triggered | When may expensive semantic computation affect flight? |
| Safety boundary | planner and shield present or absent, verifier optional | Is semantic competence separable from physical safety? |
| Progress and recovery | implicit / periodic monitor / triggered reasoner | Who notices that the mission has stopped progressing? |
| Semantic memory | none / short context / compact keyframes / compact state | What history is available to semantic reasoning? |
| *(learned-action only)* action horizon | single / chunk | How much future motion is produced per inference? |

Deliberately **not** first-stage axes: model backbone and size, quantisation,
TensorRT, CUDA graphs, shared-versus-duplicated visual encoders, KV-cache
policy, detector architecture, keyframe-selector tuning. Those are deployment
parameters. Varying them during the first architecture screen would confound
functional architecture with implementation efficiency.

## Repository layout

```
configs/
  architectures/   c0 … c14, each a controlled mutation of another
  environments/    the five benchmark regimes
  models/          simulated latency/cost profiles
  experiments/     staged sweeps
src/uavlab/
  contracts/       the typed boundaries every component shares
  core/            clock, scheduler, decision router, config grammar, event log
  plugins/         perception, memory, policies, verifier, planner, shield, …
  adapters/        environments: deterministic, scene replay, and simulator stubs
  analysis/        metrics, paired statistics, Pareto surface
  experiments/     sweeps and reproducibility manifests
tests/             unit / contract / integration / smoke
docs/              architecture, diagrams, simulator boundary
```

## The most important contract

`DecisionEnvelope` is the only way a semantic output can influence motion:

```
kind: skill | waypoint | kinematic_action | action_chunk | mission_directive
payload, decision_id,
source_observation_seq, source_t_sim_ns,
produced_t_wall_ns, produced_t_sim_ns, valid_until_t_sim_ns,
confidence, provenance
```

Consequences, each of which is enforced by a test:

- **No free-form model text can reach a controller.** The controller accepts one
  typed `ControlCommand` with no text fields.
- **`mission_directive` never becomes motion.** A monitor or reasoner can change
  what the system intends, never what the motors do.
- **Latency is measured from observation to execution**, not from model entry to
  model exit — see below.

## Decision age

```
decision_age = execution_sim_time − source_observation_sim_time
```

This is a first-class metric because inference latency alone does not describe
an asynchronous system. A slow output computed from a frame that is still
operationally valid is very different from an equally slow output produced while
the vehicle has already flown several metres. Every control command carries the
observation it came from, so the difference is always visible.

## Simulated time

Timing is half the study, so simulation time is virtual and explicit. A policy
that costs 350 ms of inference *declares* it; the clock advances by 350 ms; other
roles genuinely continue during that interval. Runs are therefore concurrent,
deterministic and fast — a 90-second mission executes in well under a second, and
"asynchronous" means something reproducible rather than "whatever the OS
scheduler did".

## There is no model and no vision in this repository yet

Stated plainly, because the plugin names invite the opposite reading:

- **No VLA.** `mock_vla`, `chunk_vla` and `world_model_vla` are closed-form
  geometry — a unit vector toward a believed target position, scaled by a cruise
  speed, plus a repulsive term from the depth fan. No network, no checkpoint, no
  training.
- **No VLM or LLM.** `vlm_waypoint` and `scripted_skill` are the same kind of
  arithmetic wearing different authority levels.
- **No vision at all.** Nothing renders. `observation.rgb` is a `SensorRef`
  holding a hash of the pose; there is no pixel array behind it anywhere in the
  codebase. `grep -r "import torch\|import cv2" src/` returns nothing.
- **The "detector" is geometry.** `semantic_hits` come from the environment
  filtering its own landmark list by range, field of view and ray-cast occlusion,
  then adding Gaussian noise. `IdentityPerception` copies those straight into
  `Detection`. It performs no perception.

**What this does validate:** the contracts, the decision router, the scheduler
and simulated clock, staleness accounting, the safety boundary, the config
grammar, the metrics and the statistics. Those are all geometry-and-timing
properties, and they are genuinely exercised.

**What it cannot validate:** anything about visual grounding, visuomotor
competence, language following, or semantic generalisation — which is most of
what C1–C14 are *named* after. No table produced from these plugins is a result
about foundation-model autonomy.

Milestone D replaces one plugin per family with a real model and changes nothing
else. Until then, read every number here as a harness measurement.

## Status and honesty about the numbers

Milestones A and B are complete: contracts, plugin protocols, config grammar,
scheduler, decision router, simulated clock, event logger, deterministic
environment, and all fifteen configurations running as pure configuration.

**The shipped policies are simulated stand-ins, not real models.** They reproduce
each family's information flow and authority boundary with scripted logic and a
configured latency budget. Numbers produced with them validate *the harness* —
that the runtime is modular, deterministic and fair — and are not results about
any published system. Real LLM/VLM/VLA adapters are Milestone D; they replace
one plugin each and change nothing else.

See [EXPERIMENTS.md](EXPERIMENTS.md) for the protocol and
[docs/architecture.md](docs/architecture.md) for the runtime design.
