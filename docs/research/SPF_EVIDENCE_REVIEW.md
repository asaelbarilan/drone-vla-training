# See, Point, Fly evidence review

Search date: 2026-08-25. Protocol: `SPF_RESEARCH_PROTOCOL.md`. Machine-readable
ledger: `spf_evidence.json` (31/31 meaningful, 27 primary, 5 direct solutions,
7 dataset/benchmark sources; validated with the evidence-first validator).

## Search log

| Lane | Queries/resources inspected | Outcome |
|---|---|---|
| Exact paper | title/alias searches; arXiv 2509.22653; CoRL/PMLR 305 paper; appendices | Exact mechanism, equations, parameters, tasks, results and limitations recovered. |
| Official resources | project page; `Hu-chih-yao/see-point-fly`; supplementary; repository README, license, model client, projector, action space and all three adapters | Public source is proprietary. It is evidence only; implementation must be independent. No checkpoint exists because SPF is training-free. |
| Direct solutions | TypeFly, PIVOT, VLFly, STMR, GeoNav | SPF differs causally by asking the VLM to produce a point and distance label directly rather than a skill, map action or selected candidate. |
| Grounding foundations | RT-Trajectory, MOKA, SpatialVLM, SpatialRGPT, visual-goal prediction | Image-space intermediates are established, but quantitative range/spatial output is model dependent. |
| Aerial benchmarks | AerialVLN, CityNav, OpenUAV/TravelUAV, OpenFly, AVDN, DRL simulator | The deterministic simulator is a first-stage capability gate, not a reproduction of SPF's DRL scenes. |
| Later systems | OnFly, AerialVLA, PMR, CognitiveDrone-R1, FLIGHT | Their verifier, monitor, direct-action, recovery or chunking mechanisms must not be folded into C2. |
| Local resources | Ollama inventory and official Qwen3-VL model card/license | `qwen3-vl:8b` is already installed, visually capable and Apache-2.0 licensed; it is the local candidate to test. |

Technical claims use primary papers and official resources. Third-party result
pages were discovery aids only and were not retained as technical evidence.

## Evidence table

| ID | Category | Inspection | Decision contribution |
|---|---|---|---|
| spf | direct solution | full text | Defines RGB+instruction to point+distance, nonlinear scale and reactive loop. |
| spf-code | direct solution | resource | Confirms schemas/adapters; proprietary, so no code reuse. |
| typefly | direct solution | methods/results | Textual bounded skills are C1, not C2. |
| pivot | direct solution | methods/results | Candidate-mark selection is the closest non-SPF point baseline. |
| aerialvln | dataset/benchmark | methods/results | Foundational learned aerial VLN benchmark. |
| citynav | dataset/benchmark | methods/results | Language-goal aerial navigation benchmark. |
| openuav | dataset/benchmark | methods/results | Continuous target-oriented platform/benchmark. |
| openfly | dataset/benchmark | methods/results | Large-scale aerial VLN toolchain. |
| stmr | alternative | methods/results | Growing semantic map plus LLM action alternative. |
| geonav | alternative | methods/results | Geographic coarse-to-fine map/graph alternative. |
| cognitive-drone | alternative | methods/results | Direct VLA plus slow reasoner; later family. |
| uav-vla | alternative | methods/results | Satellite mission generation, different authority. |
| rt-trajectory | grounding | methods/results | Image trajectory intermediate precedent. |
| moka | grounding | methods/results | Mark-based embodied grounding precedent. |
| spatialvlm | grounding | methods/results | Spatial competence depends on model/data. |
| spatialrgpt | grounding | methods/results | Depth/region grounding is learned, not guaranteed. |
| navagent | alternative | methods/results | Multi-scale trained urban VLN alternative. |
| avdn | dataset/benchmark | methods/results | Dialog/ambiguity aerial benchmark. |
| vlfly | direct solution | methods/results | RGB open-vocabulary waypoint/control alternative. |
| aerialvla-min | alternative | methods/results | Selected later direct-action representative. |
| onfly | alternative | methods/results | Selected later verifier/monitor/memory system. |
| aerialclaw | alternative | full text | Frozen skill-authority comparator. |
| pmr | alternative | methods/results | Selected later recovery-only system. |
| flight | alternative | methods/results | Selected later asynchronous action-chunk system. |
| qwen3vl | resource | model/resource | Loadable local VLM candidate. |
| gemini | resource | model/resource | Paper-default closed cloud reference. |
| drlsim | dataset/benchmark | resource | Paper simulator; not installed local substrate. |
| gemini-robotics | grounding | methods/results | General embodied spatial grounding evidence. |
| camera-goal | grounding | methods/results | Visual-goal prediction predecessor. |
| quadcopter-il | dataset/benchmark | methods/results | Early continuous 3-D instruction following. |
| openvla | resource | methods/results | Direct-action VLA backbone; not waypoint grounding. |

## Mechanism taxonomy

The reviewed systems separate cleanly along the authority boundary:

1. **Language to bounded skills/programs** — TypeFly and AerialClaw.
2. **Language+image to waypoint/point** — SPF, PIVOT and VLFly.
3. **Map/graph-mediated action** — STMR and GeoNav.
4. **Learned direct action** — CognitiveDrone and AerialVLA.
5. **Supervised hierarchy/chunks/recovery** — OnFly, PMR and FLIGHT.

SPF belongs only in group 2. Adding OnFly's verifier/memory, AerialVLA's action
head, or FLIGHT's action chunks would make C2 a hybrid and destroy the intended
family comparison.

## Resource inventory

| Resource | Availability | License/provenance | Use in C2 |
|---|---|---|---|
| SPF paper + supplement | available | paper HTML/PDF is CC BY 4.0 | Equations, parameters, protocol and limitations. |
| SPF official source | cloned at `5621bcf...` | proprietary | Behavioral audit only; no copied code or prompts. |
| SPF weights/training data | not applicable | training-free | None required. |
| Gemini 2.0 Flash | API only | provider terms | Paper reference, not valid local dependency. |
| Qwen3-VL 8B | installed as `qwen3-vl:8b`, digest `901cae732162` | Apache 2.0 official model/repo | Candidate normalized frozen VLM. |
| Gemma 3 4B | installed; digest `a2af6cc3eb7f` | Gemma terms | Rejected by locked probe: centered target mapped to `(5,5)`. |
| Qwen3-VL 2B | installed; digest `0635d9d857d4` | Apache 2.0 | Rejected: close-range labels are non-monotonic. |
| Gemma 4 e2b | installed; digest `7fbdbf8f5e45` | Apache 2.0 | Rejected: constant label 5 over 12-2 m. |
| Gemma 3 12B | downloaded; digest `f4031aab637d` | Gemma terms | Rejected: better point grounding, but no near label at 1.5-2 m. |
| Local RGB camera | available | testbed renderer | The only semantic model input, plus mission text and camera intrinsics. |
| RGB-D depth | available but excluded | shared sensor | Not consumed by SPF policy; geometry remains with SUPER. |
| Router/SUPER/controller | frozen and accepted | testbed substrate | Common execution normalization after `WaypointGoal`; C2 has no C3 verifier. |

## Evidence synthesis

SPF's irreducible mechanism is `RGB + instruction -> (u, v, d_label)` on every
semantic cycle. The integer label is intended travel distance, not measured
depth. The paper maps it with

`d = max(0.1, 10 * (d_label / 10) ** 1.8)`

and lifts the normalized pixel through horizontal/vertical half-FOV into a
body-frame 3-D displacement. This is the representation that must survive the
benchmark normalization. A fixed 12 m hop, depth-at-pixel range, semantic
detector, renderer color rule, goal coordinates or scripted search pattern
would change the causal system and cannot satisfy the SPF gate.

The paper executes yaw/pitch/throttle primitives directly. C2 instead converts
the same displacement to an absolute ENU `WaypointGoal`, then uses the shared
router, SUPER and controller. This intentionally removes paper-specific
flight-control competence while preserving semantic waypoint authority. The
deviation must be visible in logs and documentation.

The paper says the loop repeats until the instruction is fulfilled, while the
public simulator loop is manually interrupted and its point schema has no
explicit terminal token. The public Tello adaptive path treats labels 1-2 as
too close for forward travel. Because this benchmark requires an autonomous
terminal decision, two consecutive valid target-grounded labels at or below 2
are normalized to an explicit `STOP`. This rule is predeclared and observable;
it uses model output only, not scoring distance or depth.

## Options considered

### A. Run the official repository with Gemini

Highest paper-backend similarity, but invalid for a clean local gate: cloud
credentials and mutable service behavior undermine reproducibility, and the
repository license forbids copying/modification.

### B. Clean-room SPF plugin with local Qwen3-VL 8B — selected

Independently implement the published schema/equations behind the testbed
interfaces, call a real already-installed Apache-2.0 VLM, fail closed on
unavailable/invalid output, and normalize only execution below the waypoint.
This is the smallest faithful and reproducible option.

### C. Rename the existing Gemma RGB-D point policy

Rejected. It predicts `found/arrived`, uses a fixed hop and reads metric depth
at the grounded pixel. Those are useful diagnostics, but they are not SPF's
point-plus-discrete-distance mechanism.

## Implementation plan

1. Freeze the schema, equations, termination normalization, local model profile,
   development seeds and gate in `SPF_IMPLEMENTATION_LOCK.md`.
2. Probe Qwen3-VL 8B on frames generated only from the predeclared development
   seeds, testing JSON validity, point grounding and distance-label monotonicity.
3. Implement a new clean-room `spf_waypoint` policy; do not mutate the legacy
   Gemma policy and do not consume depth/semantic hits/privileged state.
4. Add a C2 SPF configuration and unit/contract tests for schema validation,
   adaptive scaling, camera lift, ENU transform, two-confirmation stop and
   fail-closed behavior.
5. Run the predeclared local gate, tune only generic prompt/model/runtime
   parameters on seeds 1040-1044, then freeze or document a genuine blocker.
6. Run focused tests, configuration validation, Ruff and the complete regression
   suite before moving to AerialVLA.
