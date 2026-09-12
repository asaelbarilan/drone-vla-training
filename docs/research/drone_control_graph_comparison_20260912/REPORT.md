# D-100: drone_control search audit and matched planning comparison

Status: source audit complete; comparison specified; implementation and navigation
performance UNVERIFIED. No runtime edits, simulator connections, model requests,
new flights or source-project modifications. The user authorized inspecting
`drone_control` and defining the comparison discussed after D-99.

## What was found

There are two relevant paths in drone_control. They must not be conflated.

| Path | Model authority | Classical responsibility | Source evidence |
| --- | --- | --- | --- |
| HybridAgent / frontier_graph_yolo | Mission-step generation and possible failure replanning; some instructions use heuristic plans before any LLM call | Entire graph SEARCH: frontier generation, feasible viewpoints, choice/order, leg execution, scanning and visited/failed state | `mission_planner.py:243`, `pilot.py:1353`, `graph_search.py:55`, `viewpoint_graph.py:449` |
| HierarchicalAgent / bounded region menu | Selects an ordered list of offered region IDs, then IDs are resolved into stored world waypoints | Generates candidate regions; gates and executes proposals | `hierarchical_agent.py:4088`, `ollama_waypointer.py:1335` |

The first is the closest match to the user's frontier/viewpoint graph description.
It is VERIFIED by source inspection to choose individual viewpoints classically:
`GraphSearchSession.run` calls `ViewpointGraph.next_goal`; pending candidates are
scored and optionally ordered by a classical tour/parallax rule. It does not call
the LLM to choose the next node. This does not dispute the user's observation that
it searched better; it identifies which component performed that work.

The second path already contains a partial implementation of the model-choice
interface proposed in the discussion. Its optional frontier menu is OFF by default
(`VLA_MENU_FRONTIER=0`); the default menu is a compass/range lattice. When enabled,
frontier regions are appended to the lattice, not substituted for it. We did not
read runtime environment files, so actual activation in any past run is unverified.
The current Valley/operator branch is a different task and was not launched.

Source checkout: `070f2dab42949de034d9546c4f79356d9e746ee5`, tracked working tree
clean at inspection. Exact file hashes and checked line ranges are in
`SOURCE_AUDIT.json`. Historical run outcomes in comments/docs were not independently
rescored during this audit; none is imported as a benchmark result.

## Reusable mechanisms and limits

1. **Reachable viewpoint generation.** `FrontierSearch.propose_neighbors` selects
   standoffs near free/unknown boundaries, computes known-free A* routes, scores
   actual route length, and records route clearance. A viewpoint includes position
   AND viewing yaw. This addresses where to stand and look before moving further.
2. **Persistent execution state.** Nodes record scanned status; edges record done
   and failed status. `_in_flight_edge` binds arrival to the issued choice rather
   than whichever candidate happens to rank first later. A graph search session
   persists across its flight legs, but is reset for a new SEARCH subgoal.
3. **Model selection by ID.** The hierarchical path resolves model-returned IDs
   against the offered menu and produces world-coordinate proposals. This interface
   can be adapted without allowing the model to invent metric destinations.
4. **Existing pitfalls must remain visible.** Frontier IDs `R_F1...` are re-enumerated
   from the current ranking, so identity can change between calls. The optional
   frontier-menu reachability check fails open if the planner is absent or throws.
   It computes viewpoint yaw but does not carry that yaw in SearchRegionHypothesis.
   Its wording equates frontier-cell count with newly observable area, which is not
   an independently measured information gain. Do not copy these semantics blindly.
5. **Graph limitations.** The older viewpoint structure primarily adds parent/child
   edges plus backtracking; it is not a general globally optimized route graph.
   Source comments recommending tree/tour changes are historical hypotheses, not
   proof that all alternative routes or a globally optimal search are available.

The source graph profile includes map-specific or scale-specific choices: broad
path-clearance threshold 6 m, large travel speeds/tolerances, scans, YOLO/OWLv2
perception, NED coordinates, and AirSim or optional ORB-SLAM pose. Its directional
Blocks-map bias exists but is disabled in the checked graph profiles. None of these
is a justified default for the 0.6 m/s, 90 s paper task. Cloud fallback, operator
selection, physical-touch endgames, ground-truth hooks and live environment-variable
bundles are outside the proposed adaptation.

## The comparison to build

Keep the existing red-tower task as a minimum competence gate. Compare these named
variants; names below are design labels, not existing executable configurations.

| Variant | Where the next destination comes from | Purpose |
| --- | --- | --- |
| Graph / classical selector | Fixed classical rule over the shared viewpoint graph | Reference for the graph representation and execution |
| Graph / Gemma selector | The same resident gemma4:e2b chooses a candidate ID from that graph | Measures the effect of model-based viewpoint selection |
| Current C5 | Frozen image-point policy + monitor + SUPER | End-to-end context for a different representation and control flow |

The PRIMARY causal comparison is the two graph selectors. C5 differs in memory,
representation, goal persistence and observation interface; a graph-versus-C5
outcome alone cannot assign the effect specifically to reasoning or graph memory.
The graph/classical arm is classical in its SELECTOR. If both arms share model-based
target perception, it must not be labeled an entirely model-free system.

### Shared components in the two graph variants

- Identical raw RGB, corrected depth, odometry and geometric range-fan access.
  No simulator target positions, semantic_hits from the adapter, privileged map,
  scripted red-pixel detector or human-selected target enters the policy.
- Identical online mapping, frontier/viewpoint generation and candidate filtering;
  candidates and execution feedback come through an explicit typed perception/state
  extension. Do not hide map objects in string notes or expose SUPER private state.
- Identical visual target evidence, target-memory update, target-approach candidate
  construction and terminal monitor. Grounding must be image-derived and validated
  on saved frames before a flight comparison. The existing monitor does not yet
  establish a reliable target-localization interface; that dependency is OPEN.
- Identical semantic goal commitment, blocked/arrived handling, scan behavior,
  planning cadence, geometric admission, SUPER and controller parameters. Turning
  toward a viewpoint is an explicit common observation action; its cost is charged.
- Same task, start distribution, mission limits and success rule. Ground truth is
  used only for offline evaluation/debugger overlays, never runtime decisions.

"Same graph" means identical generation code and state for a matched observation
snapshot. Once two closed-loop paths diverge they naturally collect different
observations and graphs. Do not force one arm's map into the other after divergence.

### Candidate and persistence contract

A candidate snapshot carries source observation/time, map revision, immutable
candidate ID, kind (frontier, target approach or observation-only action), ENU pose,
viewing yaw, route/clearance evidence, measured or explicitly proxy gain, visited/
failed state, and references to supporting images. The model also receives the
mission, current pose and compact history. The classical selector receives the same
candidate facts. Separate candidate metadata from simulator scoring truth.

Gemma returns a candidate ID tied to the snapshot revision, with an optional short
reason. Start with one next-viewpoint choice rather than adding a multi-node plan,
value-map model and new detector at once. This tests next-viewpoint planning, not
proof of full multi-step planning. Preserve the selected world goal until arrival,
invalidity or an explicit replan event; ordinary low-level SUPER replans do not
replace it. Revalidate the selected candidate at activation. Retired or stale IDs
are rejected and logged; never silently remapped to a different location. Invalid
output counts as model-selection failure; any classical fallback is separately
logged and cannot masquerade as a successful Gemma choice.

IDs must survive reordering and graph updates. A split/merge has explicit identity
handling and version invalidation. Arrival plus actual observation marks a viewpoint
visited; merely issuing a goal does not. Both selectors share all these rules.
Candidate shortlisting, switching criteria and timeouts are fixed before comparing
selectors, derived from sensor/vehicle requirements and recorded in configuration.

### Mapping and execution boundary

`uavlab` already exposes RGB/depth refs, odometry and a horizontal range fan. SUPER
uses only the fan, with expiring free/occupied evidence; exploratory routes may
cross unknown cells, while committed motion/backup must be safe. It is not a ready
persistent frontier map. `OccupancyHint` currently has no frontier/candidate schema.

Build an explicit shared observation-derived exploration map upstream of the
selectors. Keep SUPER unchanged. Start with available measured geometry; missing
camera depth is UNKNOWN, not evidence of a free corridor. Horizontal rays at one
altitude do not certify a vertical column or an altitude change. The offline mapping
gate must establish adequate free-space connectivity and height handling before
claiming candidate reachability. If it fails, record the sensing/interface limit
rather than making unknown cells free. A route certificate supports the candidate;
SUPER remains the authority for actual motion and may still reject it.

Do not import AirSim/A* execution into the paper runtime. Adapt the pure graph,
candidate identity and scoring interfaces. Normalize units and coordinate frames:
NED (north,east,down) -> ENU (east,north,up); adapt yaw by physical direction, not just
copying a signed angle. Do not copy arena coordinates, range caps or 6 m clearance
constants. Any new semantic candidate contract and geometric admission type must be
opt-in; the frozen pixel-specific C5 verifier/profiles remain unchanged.

## Staged validation and what each stage can establish

1. **Offline contract gate, zero model calls.** Use saved observations from the
   three corrected-depth runs to construct and display the map, candidates, IDs,
   viewing directions, route evidence and exclusions. Check transformed coordinates,
   unknown-space handling, obstacle inflation, stale-ID rejection and visited/failed
   updates on synthetic known-answer cases. Ground truth can test geometry offline
   but never supply candidates. This validates the shared candidate mechanism,
   not autonomous search performance. Do not tune against held-out seeds 1–40.
2. **Matched saved-state choice diagnostic.** After that gate, fix the observation
   snapshots/candidate menus before inference and compare classical and Gemma choices.
   Include obstruction, target loss, exhausted branches, alternative viewpoints and
   invalidated goals. Record fallback rate and whether the model changes a meaningful
   decision. Offline chosen outcomes cannot predict the unobserved closed-loop future.
   Calls and sample size must be bounded in a separate preflight record.
3. **Matched closed-loop screen.** Only after geometry and shared grounding gates,
   freeze both graph configs and test paired development seeds. Use 1060–1064 as the
   candidate development set; number/order/call budget are specified before launch.
   Primary score remains stopping correctly within 2 m by 90 s, with collision and
   false-stop failures. Also report coverage, redundant revisits, time after losing
   target evidence, closest approach, accepted choices, fallbacks and inference cost.
   Do not silently lengthen the horizon or relax success because search needs time.

For the decision-only diagnostic, both selectors see the same frozen snapshots.
For flights, report actual model compute/call cost and charged simulated latency;
classical selection does not receive fictitious model calls. A matched-delay
classical control is needed if a performance difference is attributed specifically
to choice quality rather than inference delay. It is a declared timing control, not
another hidden variant. Shared perception cost is counted for both arms.

If both graph selectors succeed, the structured stack is sufficient on this gate;
it does not prove Gemma improves planning. If Gemma improves on the matched classical
selector, test whether that survives the delay control and additional seeds. If
classical succeeds and Gemma fails, inspect identical candidate choices and costs.
If neither succeeds, return to the shared map/perception/execution evidence before
blaming the selector. If the basic task produces mostly one-candidate decisions,
it cannot measure semantic planning benefit; a later explicit search-task study
would need a separately defined task distribution.

## Research scope and next step

This is an adaptation of user-owned code, informed by the previously validated
24-primary-work review, not a new faithful OnFly/VLFM reproduction. The source
mechanisms align with reviewed categories: `vlfm` (geometric frontiers plus semantic
value), `lmnav` (topological structure), `vlmnav`/`pivot` (executable candidates), and
`onfly` (local image goals with monitoring). See the existing [evidence matrix](../c5_navigation_audit_20260910/evidence.md)
and [review](../c5_navigation_audit_20260910/REPORT.md). No new literature sweep or
claim of current third-party code/weight availability was made in this audit.

Next implementation unit: typed candidate snapshot + persistent identity +
observation-derived map adapter, with the offline debugger contract gate. Reuse
GraphNode/GraphEdge and candidate-resolution ideas; do not transplant the entire
mission stack. This is ready to implement as a named architecture addition; it is
not implemented or flight-validated by this document. No additional flights are
active or scheduled.
