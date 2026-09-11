# Why C5 is failing the basic navigation task

Research audit, 10 September 2026. Decision D-85. This review used public papers, official repositories and existing local traces; it made no model inference calls and changed no navigation implementation.

## Finding

Keep the task. It is a useful minimum competence test. Current evidence does **not** establish that C5, VLM navigation generally, or planning generally cannot solve it. It establishes that our tested configurations fail, with both visual grounding errors and material differences from the source architecture still present.

The most actionable newly identified difference is **camera yaw during obstacle avoidance**. The source method maintains orientation toward the proposed goal; our controller faces a carrot on the local path. That is a concrete implementation difference, but its contribution to failure remains a hypothesis until an isolated intervention tests it. Replacing models repeatedly would not resolve that uncertainty.

The research also contradicts the assumption that model quality has already been ruled out. Published within-system ablations show model effects; our repaired Gemma trace still contains substantial grounding error. Implementation and model limitations can interact.

## What successful systems actually do

These are mechanism comparisons, not a cross-paper leaderboard: tasks, thresholds, observations, checkpoints and simulator behavior differ.

| Work | What surrounds the language/vision model | Evidence relevant here |
|---|---|---|
| [OnFly](https://arxiv.org/html/2603.10682v1) | Dual-rate policy/monitor, visual memory, semantic/depth waypoint refinement, Fast-Planner and goal-facing yaw | Full SR 67.8%; no verification 63.7%; no planner 35.8%; 2B model 43.4% versus 4B 67.8%. Both integration and model matter. |
| [See, Point, Fly](https://arxiv.org/html/2509.22653v1) | Predicts an image point **and intended travel amount**, then maps these into reactive movement | Its same-Gemini-2-Flash comparison reports plaintext 7%, PIVOT 40%, SPF 100% on the comparison task set. Interface matters even with the backbone held fixed. This is not a universal success rate. |
| [Fly0 v2](https://arxiv.org/html/2602.15875v2) | Region grounding, uncertainty-aware depth, free-space target construction and a persistent world anchor between semantic updates | Avoids redefining the world goal from every new image. A stable anchor can still refer to the wrong object. |
| [VLMnav](https://arxiv.org/html/2411.05755) | Depth/pose-based navigable action proposals marked on the image, plus a separate stopping decision | SR 50.4%, but 12.9% when simulator obstacle sliding is disabled. A published success can depend strongly on execution assumptions. |
| [PIVOT](https://arxiv.org/html/2402.07872) | Iteratively marks and refines action candidates; navigation actions use depth and bounded motion | It simplifies action selection through visual candidates, at the cost of multiple model calls per action. |
| [TypeFly](https://arxiv.org/html/2312.14950) | LLM plans call MiniSpec skills; object detections supply location, size and color | “LLM controls a drone” does not mean the LLM independently solved visual grounding. |
| [STMR](https://arxiv.org/html/2410.08500) | Grounding DINO, Tokenize Anything and depth construct a semantic/metric representation for LLM reasoning | A structured spatial interface supplies information that is difficult to infer from raw pixels. |
| [VLFM](https://arxiv.org/html/2312.03275) | Vision-language value map, depth-based frontiers, object detection and a pretrained point-navigation policy | Zero-shot semantic transfer does not mean every navigation component is untrained. |
| [LM-Nav](https://arxiv.org/html/2207.04429), [VLMaps](https://arxiv.org/html/2210.05714) | Respectively, a prior observation graph with learned navigation; or a posed RGB-D semantic map | Their map, pose and controller contracts are part of the solution. |
| [NaVid](https://arxiv.org/html/2402.15852), [OpenFly](https://arxiv.org/html/2502.18041) | Navigation training, temporal representation and action decoding | Their results do not establish that an arbitrary small chat VLM plus image history is an equivalent policy. |

The recurring pattern is a VLM connected to a carefully defined spatial representation and executable action interface. Some methods learn that connection; others supply it through geometry, detectors, maps or visual action candidates. This supports investigating our interface while retaining the task. It does not guarantee that every backbone will succeed once the interface is repaired.

Simple images are not necessarily easy for a VLM: [BlindTest](https://arxiv.org/html/2407.06581) documents failures on elementary visual geometry. That is a reason to measure grounding directly, not evidence that our particular checkpoint must fail. [NavBench](https://arxiv.org/html/2506.01031) separately measures scene understanding, global planning, progress tracking and local action choice, illustrating why aggregate navigation failure cannot identify which capability failed.

## Source-to-implementation audit

The existing [implementation lock](../ONFLY_IMPLEMENTATION_LOCK.md) already identifies C5 as a clean-room adaptation to a normalized substrate. The [official OnFly repository](https://github.com/Robotics-STAR-Lab/OnFly) still advertises code coming soon at this audit. We cannot call local C5 an exact source/checkpoint reproduction.

Published details used for the audit: OnFly describes goal-bearing yaw regularization during avoidance, feature-connected semantic waypoint refinement, a Qwen3-VL-4B-AWQ backbone, 720p simulation images and a 5 m success threshold. See its methods and evaluation sections. These establish comparison points, not proof that every difference causes our failure. [Source](https://arxiv.org/html/2603.10682v1)

| Contract | Local evidence | Implication and confidence |
|---|---|---|
| Camera orientation while translating | `src/uavlab/plugins/planning/super.py:515` derives trajectory yaw from segment direction. `src/uavlab/plugins/control/mock.py:53` tracks a path carrot; `:109` computes yaw toward that carrot. The controller does not consume a separate semantic-goal yaw command. | **Verified discrepancy; untested cause.** Detouring can turn the camera away from the desired object. Changing only stored trajectory yaw would not fix the controller. |
| Semantic waypoint refinement | `OnFlySemanticGeometricVerifier` in `src/uavlab/plugins/reasoning/onfly.py` explicitly lacks cached ViT feature masks; local checks cover geometry/provenance and the endpoint gate. | **Verified omission.** Could leave a near-object point uncorrected. The source ablation above argues against assuming this omission alone explains complete failure. |
| Image geometry | Local images are 224×224 with 90° horizontal FOV and square-camera geometry. | Different target detail and vertical FOV. Resolution/domain sensitivity needs a matched-image check; it is not proof the task is invalid. |
| Model/runtime | Active local model is repaired `gemma4:e2b`, not the source checkpoint. Earlier runtime/model-label errors are documented in D-71 and D-74–D-78. | Historical broken or mislabeled runs cannot establish independent model failures. Current repaired runs remain valid observations of their own configuration. |
| Arrival and stopping | Local primary gate requires autonomous stop within 2 m. | Stricter than the cited source. However, the audited repaired flight never approaches within 5 m either, so threshold alone cannot explain it. |
| Memory/monitor | Local image-history/contact-sheet and expanded monitor/target-bound stopping differ from feature caching and the source monitor interface. | Adaptation, not equivalence. A change here must be isolated rather than bundled with yaw, model and resolution. |
| Timing | Current comparisons charge fixed simulated policy/monitor latency while recording real inference time separately. | Real HTTP duration is not automatically the simulated reaction delay. Service interruptions are operational invalids, not completed navigation failures. |

The source's multi-subtask decomposition is also not fully reproduced, but it is a weak explanation for a single-target task. Prioritizing it now would add complexity without addressing the observed failures.

### Why C1 and classical success do not isolate planning

Classical/oracle success demonstrates that the task and motion substrate are executable given suitable state. It does not establish that perception supplied the same state to C5.

Local C1 uses `identity` perception. `src/uavlab/plugins/perception/identity.py:98–105` converts semantic hits into labeled detections with positions and distances. `src/uavlab/plugins/reasoning/aerialclaw.py:627–642` includes those fields in its prompt. The [AerialClaw fidelity note](../../fidelity/AerialClaw.md) documents this normalized semantic channel. C0 additionally provides an oracle ceiling.

Thus the current comparison mixes **obtaining the target state** with **planning using that state**. C1 success is useful evidence, but it is not an equal-input demonstration that an LLM plans better than a VLM. If the paper targets planning, retain end-to-end navigation as the main task and separately attribute failures to grounding, goal selection, execution and stopping. A diagnostic with supplied target state should be labeled privileged; it must not silently become the deployed C5 policy.

## What the existing flight tells us

An offline deterministic replay of `runs/c5_gemma_runtime_fixed_target_stop_20260907_s1061` reproduced logged distance exactly. It called no model. Full measurements: [replay_1061.json](replay_1061.json).

| Measurement | Observation | Interpretation |
|---|---|---|
| Decision frames | 89, target visible in 36 | Being inside sensor range or angular FOV does not guarantee an unoccluded target. |
| Visible-frame grounding | Median distance from predicted pixel to offline red-body bounding-box center: 30.13 px | Substantial error exists. Center distance is **not** an object-hit rate; measure mask/bbox membership before labeling every prediction incorrect. |
| First visible decision, 16.95 s | Target center (7,84); prediction about (67,33.5); error 78.41 px | This individual prediction is strong evidence of incorrect image localization. |
| Closest decision snapshot | 13.22 m; target bearing −87.77°, outside the forward view | At this point perception lacks a direct target view. It does not prove whether yaw, an earlier bad waypoint or both caused the situation. |
| Final distance | 20.18 m | Failure includes failure to approach, not only terminal stop calibration. |
| Movement between source image and goal activation | Mean 0.46 m, max 0.63 m; no proposed goals behind the vehicle at activation | Some staleness exists; the simple explanation that goals routinely activate behind the vehicle is unsupported on this seed. |
| Repetition | 47 of 81 comparable predictions within one pixel of the supplied previous-goal cue | Possible cue anchoring, but legitimate persistence is also possible. Requires a controlled cue ablation. |

Across five repaired target-bound Gemma development flights: **0/5 success, three timeouts, two false stops, no collisions or parse errors**. This separates safe execution and schema compliance from navigation competence. It is a small development sample, not a general capability estimate.

Historical corrected Qwen evidence includes a successful baseline flight; “no VLM ever solves this” is therefore too strong. Three matched Gemini image checks improved grounding, but cloud flights were interrupted by quota/service errors. They do not establish better completed navigation. Passing software tests likewise establishes neither source fidelity nor autonomous competence.

## Resource and reproduction options

| Option | Availability checked | Decision |
|---|---|---|
| Repair the local C5 execution contract | All relevant local code available; source paper detailed, official implementation unreleased | **First choice:** smallest intervention addressing a verified discrepancy. Keep historical/shared substrate frozen. |
| Use SPF as an external reference | Official public repo exists, but its [LICENSE](https://github.com/Hu-chih-yao/see-point-fly/blob/main/LICENSE) is proprietary and requires permission for use/copy/modification | Read the method; do not treat public visibility as permission for unrestricted reuse. Its travel-distance interface is a separate architecture comparison. |
| Study Fly0 as a metric-anchor reference | [Official repository](https://github.com/xuzhenxing1/Fly0) reported in resource inventory; Apache-2.0 metadata. Inspected code predates the July v2 paper | Cached detector uses local minimum depth and point output; v2 region/uncertainty behavior is not established by that code. Not a verified drop-in reproduction. |
| Adopt marked feasible-action candidates | Supported by VLMnav/PIVOT mechanisms; licensing/reproduction details incomplete for some resources | Plausible interface experiment after diagnosis, but changes the policy/action architecture and may increase calls. |
| Train a navigation policy | NaVid/OpenFly demonstrate task-specific training; [OpenVLA](https://arxiv.org/html/2406.09246) is a trained manipulation policy, not a ready UAV checkpoint | Not the first response to an untested controller/interface discrepancy; substantial data/compute and embodiment adaptation. |

See [resources.json](resources.json) for checked metadata and [evidence.json](evidence.json) for explicitly unverified resource fields. MIT code metadata for VLFM, VLMaps, LM-Nav and VLN-CE does not certify their weights, datasets or transitive dependencies. No resource was independently reproduced in this audit. The very recent [AirAnchor preprint](https://arxiv.org/html/2609.08442) is useful as a persistent-memory direction, but its simulator and scene-memory assumptions preclude treating it as established evidence for our cold-start task.

## Bounded next investigation

Do not change the task, switch many models, or launch another broad sweep. These are proposed stages, not experiments performed by this review.

1. **Finish the zero-call causal trace.** On existing repaired seed 1061, align target visibility, predicted pixel membership, semantic-goal bearing, path-carrot bearing and camera yaw. Inspect transitions where correct grounding precedes target loss. If loss does not follow goal/carrot divergence, downgrade the yaw hypothesis before spending inference.
2. **One isolated execution ablation, if the trace supports it.** Introduce an opt-in goal-facing yaw experiment that preserves translation planning, obstacle constraints and motion limits. Predeclare the yaw rule, retain the frozen profile, and label the intervention explicitly. Compare one matched development seed with fixed Gemma and unchanged prompts. Measure visibility retention and approach progress as well as success. If these do not improve, do not assume the source-inspired change helped.
3. **Only if grounding remains the limiting event, use a small fixed image comparison.** Select a balanced set of 12 saved observations before inference: visible near/far and absent/occluded cases. Record target membership, absent-target false positives and stop errors; keep identical image, schema and model identity logging. At most one call per image per selected model, no retries. Existing cloud quota blocks remain binding; do not start this now. Test resolution or cue changes separately from model changes.
4. **Expand only after a mechanism improves.** Run the five development seeds once for the selected change; retain failure attribution and both stopped success and diagnostic closest approach. Keep primary 2 m success unchanged; optionally report offline oracle approach at 2 m and 5 m as additional metrics. Held-out seeds 1–40 remain untouched.

Stage 2 needs a new implementation decision before editing the shared control behavior. No evidence currently justifies doing all four stages automatically or exhausting provider quotas.

## What the paper can claim

**Now:** the specified normalized small-VLM configurations fail the basic navigation gate despite collision-free execution; grounding and perception–execution integration remain confounded. This is a valid observed limitation, with checkpoint, runtime, inputs and task conditions stated.

**If the isolated execution fix improves results:** a source-to-testbed execution mismatch materially affected embodied performance. That supports a conclusion about architecture interfaces, not merely a better prompt.

**If faithful execution still fails and matched image grounding is poor:** report a model/domain grounding limitation under the tested observation conditions. The task need not be discarded.

**If grounding is reliable but goal choice/recovery remains poor:** the remaining evidence implicates the planning/memory/monitor loop more directly. That is the appropriate point to compare planning architectures with observation quality controlled.

**Not supported:** “C5 cannot solve navigation,” “VLMs are worse planners than LLMs,” or “the published method is disproved.” Those statements exceed the current implementation fidelity, matched-input evidence and sample size.

## Review coverage and limits

The [protocol](protocol.md) preceded retrieval. We screened 41 candidates and retained 24 primary works with targeted methods/results inspection, including direct solutions, benchmarks and failure analyses. The [evidence matrix](evidence.md) and machine-readable ledger record supported claims, relevance and missing information. The evidence validator checks coverage/schema, not scientific truth or independent reproduction.

Full papers were cached as text for targeted inspection; not every paragraph, supplementary asset, dependency or license was independently audited. GitHub availability reflects the retrieval date. Search/retrieval artifacts are recorded in [SEARCH_LOG.md](SEARCH_LOG.md). The leading causal claim remains explicitly untested.
