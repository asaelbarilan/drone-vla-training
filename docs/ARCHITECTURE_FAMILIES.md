# The architectures, by family

One classical control baseline and five autonomy families are the top-level
design space. The fifteen sentinel configurations C0–C14 are points in it, and
each differs from its parent by as few components as possible, so a measured
difference has one candidate explanation rather than several. Fast/slow
hierarchies are a named subfamily of the hybrid stack, not a seventh peer
family. Only the *changes* from the parent are listed — everything unstated is
inherited.

Suffixes: **g** = scripted policy replaced by Gemma 3 4B, **t** = replaced by a
trained (behaviour-cloned) network. Neither changes anything else.

On the last column: **bold** entries are papers held in `papers/small_vla/`. The
rest are the nearest published comparison recorded in each config's header —
named as the design being reproduced, not as a citation that has been checked.

---

## 1. Classical baseline — classical planner and controller only

| Config | Headline | Tweaks | Nearest published work |
|---|---|---|---|
| **C0** | Oracle ceiling | `authority: waypoint`; `allow_privileged_observations: true`; policy `oracle_waypoint` (`stop_radius_m 1.8`); shared planner `super_local`; shield `simple_collision`; 20 Hz control / 4 Hz decision | SUPER execution substrate |

The only configuration permitted to read ground truth. It answers how much
failure belongs to the flight stack rather than to semantic architecture: if C0
cannot fly, nothing measured about foundation models means anything.

## 2. LLM tool planner — mission decomposition into validated skills

| Config | Headline | Tweaks | Nearest published work |
|---|---|---|---|
| **C1** | AerialClaw skill agent | `authority: skill`; real `gpt-oss:20b` policy `aerialclaw_agent`; JSON-schema one-skill turns; SOUL/BODY plus soft skills; typed runtime validation; bounded feedback/reflection history; shared `super_local`; **1 Hz semantic cycle** | **AerialClaw** |

The accepted development gate scored 5/5 grid navigation and 5/5 object search
with zero collisions. The LLM authors every semantic hard-skill choice; the
BODY-derived coverage options use only launch pose and geometric range, never
target/scoring truth. See `docs/fidelity/AerialClaw.md`.

## 3. VLM semantic waypointer — visual target and waypoint selection

| Config | Headline | Tweaks | Nearest published work |
|---|---|---|---|
| **C2** | Point-and-fly | `authority: waypoint`; policy `vlm_waypoint` (`hop_m 12.0`, `stop_radius_m 2.0`, `stop_confidence 0.35`); planner `fixed_local`; 2 Hz decision | See-Point-Fly; the decision path of OnFly |
| **C2G** | Point-and-fly, real VLM | policy → `vlm_point_waypoint` on `gemma3:4b`; calibrated depth is sampled only at Gemma's pixel; stop requires a stable world point plus a second cropped semantic confirmation; `max_decision_age_s` 1.5 → **8.0** | as C2 |

The staleness bound had to rise more than fivefold for Gemma's decisions to be
admitted at all. That gap is itself a result about whether a model this size can
hold waypoint authority in a real-time loop.

The RGB-D terminal path prevents the measured false stops, but it does not make
Gemma capable: C2G/C3G/C6G remain 0/3 in the safe held-out gate (D-42). Depth
supplies geometry, not semantic identity; a wrong VLM pixel remains a wrong
target.

## 4. Hybrid stack — semantics → safety gate → classical execution

| Config | Headline | Tweaks | Nearest published work |
|---|---|---|---|
| **C3** | + verifier | + verifier `semantic_geometric` (`max_waypoint_distance_m 30.0`, `min_clearance_m 1.2`, `repair: true`) | — |
| **C4** | + progress monitor | `semantic_supervision: periodic_monitor`; memory `short_context` (window 5); monitor `progress` (`stop_confirmations 2`, `lost_after_s 8.0`); scheduler → `async_multi_rate`, `monitor_hz 0.5` | the monitoring loop of OnFly |
| **C5** | + keyframe memory | memory → `compact_keyframe_memory` (`capacity 6`, `min_separation_m 3.0`) — **only** the memory plugin changes | hybrid memory of OnFly; keyframe history of OpenFly |
| **C3G / C4G / C5G** | …with a real VLM | policy → Gemma 3 4B, as C2G | as above |

C5 changes exactly one plugin against C4, so a difference between them is a
memory result and can be nothing else. **The G variants do not currently
separate**: the Gemma policy never consults the belief chain, so memory and
monitor output have nowhere to land — see CHANGES.md.

### Fast/slow hierarchy subfamily — slow reasoner above a fast VLA

| Config | Headline | Tweaks | Nearest published work |
|---|---|---|---|
| **C10** | Blocking fast/slow | `semantic_supervision: periodic_reasoner`; memory `compact_semantic_state`; recovery `hierarchical_reasoner` (**`emit: directive`** — intent, never motion); `reasoner_hz 0.5`, blocking | **CognitiveDrone-R1** |
| **C11** | + action chunks | `action_horizon: chunk`, `chunk_length 4`; policy → `chunk_vla` (`replan_after 4`) | FLIGHT; ScoutVLA |
| **C12** | Non-blocking | `semantic_supervision: async_reasoner`; scheduler → `async_multi_rate` — the reasoner no longer blocks the executor | FLIGHT; **LiteVLA-H** |
| **C13** | Event-triggered | `semantic_supervision: triggered_reasoner`; + monitor `local_progress`; recovery `bounded_reasoner` (`emit: directive`); scheduler → `event_triggered`, `reasoner_hz: null`, `max_calls 8` | **LiteVLA-H** (K=3 with event override) |
| **C14** | Predictive world model | policy → `world_model_vla` (`prediction_horizon_s 1.0`) — carries target belief forward through occlusion | WorldFly |

C10→C11→C12→C13 isolates one timing property at a time: action horizon, then
blocking versus concurrent, then scheduled versus event-triggered. C14 changes
only the policy, so a gain on the occlusion regime is a world-model result.

**CognitiveDrone** reports 59.6% → 77.2% from adding a slow reasoner at
10 Hz / 2 Hz. That +17.6 pt is the effect size C8→C10 is built to detect. It
justifies the subgroup's five configurations, not a separate top-level family.

## 5. Selective recovery supervisor — reasoning only on failure or no progress

| Config | Headline | Tweaks | Nearest published work |
|---|---|---|---|
| **C6** | Triggered reasoner | `semantic_supervision: triggered_reasoner`; memory `compact_semantic_state`; monitor `local_progress` (geometric, zero inference cost; `window_s 3.0`, `min_travel_m 1.0`); recovery `bounded_reasoner` (`emit: waypoint`, `detour_m 8.0`, `stall_threshold_s 2.5`); scheduler → `event_triggered`, `cooldown_s 4.0`, **`max_calls 8`** | selective agentic recovery over a persistent mission runtime |
| **C6G** | …with a real VLM | policy → Gemma 3 4B, as C2G | as C6 |

The watcher deciding when to wake the reasoner is deliberately geometric rather
than a model. If it were itself a model call, reasoning would not actually be
absent and the compute saving would be fictional. `max_calls: 8` makes
"selective" falsifiable.

## 6. Direct VLA — learned local-action policy

| Config | Headline | Tweaks | Nearest published work |
|---|---|---|---|
| **C7** | Bare VLA | `authority: direct_vla`; `action_horizon: single`; policy `mock_vla` (`cruise_mps 3.0`, `action_duration_s 0.2`, `avoid_gain 1.2`); memory `short_context`; **no planner, no shield**; 10 Hz decision | AeroVLA; **CognitiveDrone**; UAV-Flow |
| **C8** | + safety shield | + shield `simple_collision` (`reaction_time_s 0.35`, `hard_stop_m 1.0`, `brake_margin_m 1.5`, `allow_deflection true`) | — |
| **C9** | + keyframe history | memory → `compact_keyframe_memory` (`capacity 6`, `min_separation_m 3.0`) | keyframe/history design of OpenFly |
| **C7T / C8T** | …with a trained policy | policy → `learned_visuomotor` on a trained checkpoint; `yaw_mode: course_aligned`; `terminate_consecutive 3`; `min_terminal_speed_mps 1.5`; inference charged as a 0.01 s constant | **GRaD-Nav++**; **Exp2VLA**; **AerialVLA** |

C7→C8 adds one component and nothing else, so the safety finding is a property
of the architecture rather than of the policy in the slot. **C7T/C8T are a
working pipeline carrying a policy that does not navigate** (success 0.03) —
their numbers are not an architecture result.

---

## Papers held on disk

`papers/small_vla/README.md` has one line each on what was taken from them.
`docs/SMALL_VLA_SEARCH.md` records the search that produced them and its
negative result: no small off-the-shelf aerial VLA exists to drop into C7–C14,
because small VLAs exist where manipulation datasets exist. Both drone papers
that solved it generated their own expert data in simulation, which is what
C7T/C8T do.
