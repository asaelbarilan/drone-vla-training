# Drone VLA results audit — D149, 2026-09-19

Your suspicion was justified: our comparison contained a real decoder error, and it still cannot establish that our small adapters fly better than openfly_vla. The literature also does not support expecting an aerial VLA to get almost everything right simply because it was trained on the dataset.

This review inspects methods and results from **15 aerial learned-action architecture papers**, plus three aerial benchmarks and one assisted-navigation boundary case. All main entries control aerial agents; no manipulation-only VLA is counted. The implementations span velocity, body-rate, primitive and waypoint policies, so “drone VLA” does not imply an identical control interface. Thirty-one candidates were screened. Reported numbers below are the authors’ results, not our reproductions; several sources are recent preprints.

## The 15 architecture papers

SR means success rate under each row’s own protocol. **Do not rank across rows.** CognitiveDrone reports a normalized cognitive benchmark score, not general flight SR. Seen/unseen applies to the particular scene, object or task split specified below.

| Paper / version | Author-reported result | What was tested / key qualification |
|---|---|---|
| [OpenFly-Agent](https://arxiv.org/abs/2502.18041v7) (2502.18041v7) | SR 34.3% seen / 22.6% unseen; real-flight SR 26.09% on 23 trials. | Long outdoor routes, stopping within20m; real result includes a trajectory planner and MPC. |
| [CognitiveDrone](https://arxiv.org/abs/2503.01378v1) (2503.01378v1) | Normalized benchmark score 59.6% base / 77.2% R1 reasoning variant. | Reasoning/gate decisions in simulation; base versus reasoning-assisted variant. |
| [RaceVLA](https://arxiv.org/abs/2503.02572v1) (2503.02572v1) | Real task-category results: visual 79.6%, motion 75.0%, physical 50.0%, semantic 45.5%. | Real-drone category tests; not OpenFly routes or a single universal score. |
| [AutoFly](https://arxiv.org/abs/2602.09657v1) (2602.09657v1) | Simulation overall SR 47.9%, CR 21.9%; real indoor/outdoor SR 60% / 55%. | Target approach within5m plus15-degree alignment; real training demonstrations included. |
| [AerialVLA / AeroVLA (Xu et al.)](https://arxiv.org/abs/2603.14363v1) (2603.14363v1) | SR 47.96% seen / 56.60% unseen objects / 37.58% unseen maps. | TravelUAV simulation; seen / unseen objects / unseen maps are separate splits. |
| [SpatialFly](https://arxiv.org/abs/2603.21046v2) (2603.21046v2) | Full-training SR 38.54% seen / 25.46% combined unseen / 13.57% unseen maps. | OpenUAV; full training-data result, with extra geometric features. |
| [LongFly](https://arxiv.org/abs/2512.22010v1) (2512.22010v1) | SR 36.39% seen / 43.87% unseen objects / 11.27% unseen maps. | OpenUAV; unseen map transfer remains difficult despite history. |
| [FLIGHTVLA / Think Like a Pilot](https://arxiv.org/abs/2606.06836v1) (2606.06836v1) | Long-horizon Flow SR 59.0%; Fine-grained VLN SR 13.5% and instruction-adherence SR 11.0%. | Two different tasks: complete the Flow subtask sequence versus fine-grained route navigation. |
| [WorldVLN](https://arxiv.org/abs/2605.15964v1) (2605.15964v1) | UAV-Flow-Sim SR 79.12% fixed-language / 78.02% open-language; IndoorUAV-VLA SR 41.76%. | Flow and IndoorUAV use different completion criteria and training adaptations. |
| [ImagineUAV](https://arxiv.org/abs/2606.01205v2) (2606.01205v2) | Flow-Sim SR 70.9% full / 68.9% distilled; real flights 13/20 with planner versus 9/20 without. | A learned world-action model plus planner; only20 real trials. |
| [Exp2VLA](https://arxiv.org/abs/2607.03146v1) (2607.03146v1) | pi0.5: 84.10% single-object, 65.0% multicolor, 51.7% color-permuted; SmolVLA: 46.60% single-object and 15.0% multicolor. | Simple object approach in Isaac Lab; SmolVLA is not our SmolVLM adapter. Reporting caveats below. |
| [FSD-VLN](https://arxiv.org/abs/2607.08359v1) (2607.08359v1) | SR 26.7% seen /13.6% unseen; authors reproduce OpenFly at 18.5% /5.1% on their own test set. | Own urban split. Its reproduced OpenFly result is not the original paper protocol. |
| [UAV-Track VLA](https://arxiv.org/abs/2604.02241v2) (2604.02241v2) | Far pedestrian tracking SR 61.76% seen /55.00% unseen; vehicles 37.88% /27.91%. | Moving-target tracking survival in CARLA; not endpoint navigation. |
| [VLA-AN](https://arxiv.org/abs/2512.15258v2) (2512.15258v2) | Table 3 reports 98.1% object-navigation and 85.7% long-horizon SR. | Own tasks with depth/geometric correction; trial counts/tolerances not located. |
| [GRaD-Nav++](https://arxiv.org/abs/2506.14009v2) (2506.14009v2) | Real two-stage tasks:16/24 trained and6/12 unseen combinations; simulation table20/24 and9/12. | Real gate+object tasks, known primitives in new combinations; small denominators. |

## What changes our interpretation

**1. We cited an older OpenFly revision.** The [v7 paper](https://arxiv.org/html/2502.18041v7) reports34.3% seen /22.6% unseen SR. D146–D148 cited v6’s33.2% /10.7%. Preserve those historical records, but use v7 for the current literature summary. Neither revision’s score is established for our downloaded checkpoint. Its matching training run, release revision and normalization remain part of the reproduction audit. The [public model repository](https://huggingface.co/IPEC-COMMUNITY/openfly-agent-7b) metadata reports its last update as 2025-08-29, before v7 dated 2026-03-01. That is a concrete version question, not proof that the checkpoint differs from the paper experiment.

**2. Our decoder really did change the apparent result.** In [D148](../../../reports/vla_openfly_routes_20260919/REPORT.md), the same campus TRAIN-episode tokens produced 12/15 correct directions and 15/15 valid actions with the verified source normalization, but 0/15 valid actions with the wrong vertical profile. On the altitude TRAIN episode, source-faithful decoding still gave 7/19 directions; the training-interface control improved that to 10/19. The repair explains some failures, not all. Future images occurred in 4/34 stored steps, but removing them changed no generated tokens on these two samples. That defect is not a demonstrated cause of those remaining errors.

**3. Action agreement and successful flight answer different questions.** A recorded teacher may fly forward 3 m; a model may choose a valid 6 m macro action. Strict next-action scoring can reject it without testing whether the resulting route succeeds. Conversely, many plausible actions can still accumulate into a failed flight. Our sampled TRAIN records are useful interface diagnostics; they are neither the published held-out benchmark nor proof of generalization. The D144 pilots also failed all six local flights. We have no flight-performance evidence that Qwen is better than openfly_vla.

**4. Task and control details can dominate the number.** [FLIGHTVLA](https://arxiv.org/abs/2606.06836v1) reports 59.0% on long-horizon Flow but 13.5% on fine-grained VLN. [IndoorUAV](https://arxiv.org/abs/2512.19024v1) requires under 0.5 m final error and under π/4 yaw error for its VLA task, versus under 2 m for its VLN task. π/4 is 45 degrees, not 4 degrees. [UAV-Flow](https://arxiv.org/abs/2505.15725v2) uses semantic trajectory completion assessed by inspection. These are not interchangeable notions of “correct.”

**5. Strong results exist, with narrower claims.** [GRaD-Nav++](https://arxiv.org/abs/2506.14009v2) demonstrates actual onboard body-rate/thrust control; its unseen tests recombine known gate/object skills. [ImagineUAV](https://arxiv.org/abs/2606.01205v2) improves real success from 9/20 to 13/20 by adding its planner. [VLA-AN](https://arxiv.org/abs/2512.15258v2) reports high task-specific results, but its geometric safety module is part of the system and missing evaluation detail limits replication. High scores elsewhere do not validate our current comparison or establish that OpenFly must match them.

## Architecture and experiment implications

| Mechanism | Relevant reviewed systems | Consequence for our comparison |
|---|---|---|
| Learned velocity / primitive actions | RaceVLA, CognitiveDrone, AutoFly, OpenFly, FSD-VLN, Exp2VLA | Match dimensions, axes, units, normalization, command duration and stop semantics. |
| Learned waypoint / geometric actions | AerialVLA-Xu, LongFly, SpatialFly, VLA-AN | Record who supplies depth, state or direction hints and what the downstream planner/controller does. |
| Temporal action heads / world models | FLIGHTVLA, WorldVLN, ImagineUAV, UAV-Track VLA | Match history, chunk execution and real inference delays; single-frame scoring omits part of their design. |
| Learned low-level flight control | GRaD-Nav++ | Body rates/thrust require a different controller contract; do not silently decode them as velocities. |

The paper’s eight capability categories remain the organizing principle. OpenFly mainly covers instruction-following navigation. CognitiveDrone adds cognitive gate decisions; UAV-Track adds continuous tracking; HUGE-Bench adds inspection, orbiting, mapping and stage-wise evaluation. No reviewed checkpoint is established as covering our complete task suite or dynamic recovery requirements.

[HUGE-Bench v4](https://arxiv.org/abs/2603.19822v4) is particularly relevant to our planned experiments: its average trajectory-coverage result 0.581 and nDTW 0.467 for adaptedπ0.5 are **not 58.1% and 46.7% mission success**. It separately measures stage progress and collisions. It uses reconstructed real scenes in simulation, not evidence of physical deployment.

## Reproducibility and source-quality qualifications

Public code or a model card is not a successfully reproduced flight policy. [RESOURCES.md](RESOURCES.md) separates code, data, weight availability and licensing. OpenFly, RaceVLA, AerialVLA-Xu, WorldVLN and OpenVLA-UAV have verified model/adapter files. AutoFly’s linked model endpoint returned 401 without authentication. Several other papers have no verified matching release. Missing license metadata is unresolved, not permission to reuse.

Two similarly named AerialVLA papers must remain separate. The AAAI paper by Chen et al. is retained only as an appendix boundary case: aerial-view navigation with dialogue and privileged oracle assistance differs from unassisted first-person flight. Training-free OnFly, Fly0 and See, Point, Fly are alternative planner families, not part of the 15 learned-policy count.

Exp2VLA’s bibliography has mismatched title/identifier pairs. Its success prose mentions stabilization, while its equation/algorithm accepts radius entry; its printed 84.10% with 500 episodes needs denominator clarification. GRaD-Nav++’s simulation caption says six trials per task but printed counts do not match that denominator; its real table is internally consistent. These are reasons to reproduce and qualify the claims, not grounds to discard all results. LiteVLA-H was inspected but excluded from quantitative synthesis because the inspected report did not establish sufficiently clear test denominators/splits and full closed-loop evidence.

## Next experiment, derived from this review

**First establish a trustworthy OpenFly reference before more training or a model sweep.** This is an evaluation proposal, not a new training run.

1. Freeze the checkpoint hash, exact original packed-record subset, source statistics, camera preprocessing, instruction, causal history and primitive timing. Unknown source-profile assignments stay unscored rather than defaulting to a convenient decoder. Reproduce a small set of known source-record outputs.
2. Execute recorded expert actions in a compatible renderer/controller. Verify that labels reconstruct the intended route and that STOP refers to the navigation endpoint, including any separate descent phase. Failure here isolates data/adapter/control problems.
3. Run the model in the same development routes with new observations after each action. Show expert and model flights side by side, synchronizing image, instruction, raw tokens, decoded physical command, pose and termination reason. A recorded-video overlay is explicitly a replay, not a model-controlled flight.
4. Report action validity and per-action-family errors separately from closed-loop completion, collision rate, goal error, stage completion and inference latency. Match information access and controller assistance before comparing our adapters. Use route-level denominators and confidence intervals; do not treat frames from one route as independent flights.
5. Once the interface passes, expand route- and scene-disjoint training, retain per-source mixing, select checkpoints on development flight metrics, and evaluate all models on the same untouched split. Current small-pilot exposure does not support deployment or generalization claims.

For falsification: if expert playback fails, investigate labels/conversion/control first; if source-record outputs differ, investigate inference fidelity; if source agreement is good but flights fail, investigate accumulated error/history/timing/controller interaction. If a fully source-faithful closed-loop reproduction remains far below the relevant published setting, investigate checkpoint/release mismatch and document the unresolved reproduction gap rather than tuning on its evaluation set.

No protected seeds 1–40 or 1060–1064 were used. No model execution, training, cloud spending, baseline or split changes occurred in this review. The latest paper task categories were checked in `docs/CAPABILITY_SCENARIOS.md`; that document is context, not evidence of trained model capability.

## Audit artifacts

- [Protocol and search log](PROTOCOL.md): scope correction, inclusion/exclusion and stopping rule.
- [Evidence ledger](evidence.json):19 methods/results rows,15 main architectures,3 benchmarks,1 boundary case.
- [Candidate ledger](candidates.json):31 aerial candidates; rejected and screened-only works are identified.
- [Resource inventory](RESOURCES.md) and [raw metadata checks](resource_checks.json).
- [Pinned source versions and PDF hashes](source_manifest.json); copyrighted PDFs stay in ignored local cache.

Validation uses the evidence-first-research structural checker with `--minimum 15`, reflecting the user’s explicitly narrowed scope. Passing that check validates ledger structure, not the scientific correctness or reproducibility of authors’ claims.
