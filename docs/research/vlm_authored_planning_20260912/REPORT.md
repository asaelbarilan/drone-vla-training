# D-101: VLM-authored navigation planning

## Decision and ownership

Replace D-100's next-step classical-candidate selector direction with a new,
explicitly named **adaptive visual plan + SPF waypoint** development variant.
The model authors intermediate subgoals, their order, the active subgoal, the
expected visual change, and the next image-space point/travel distance. It receives
its previous plan and execution feedback and chooses whether to retain or revise
its destination. No frontier ranking or classical search chooses semantic goals.
SUPER still finds a feasible local trajectory to the chosen point. This is a
**new component-level adaptation**, not full MapGPT, FineCog-Nav, or a proven fix.

The user did not answer the optional candidate-versus-own-waypoint clarification
while research continued. Proceed with the stronger interpretation: the VLM
proposes its own intermediate objectives and points, not just candidate IDs.

## Primary evidence and alternatives

| Work | What the model plans | What is supplied | Decision |
|---|---|---|---|
| [MapGPT](https://arxiv.org/html/2401.07314), Sec. 3.3 | Recurrent multi-step plan, revision/backtracking, next action | Indoor navigable viewpoint graph and neighboring action options | Use adaptive-plan carryover component; do not claim graph reproduction |
| [See, Point, Fly](https://arxiv.org/abs/2509.22653) | Image point and intended travel label | Camera calibration and a nonlinear distance transform | Reuse existing tested clean-room waypoint transformation; model generates points |
| [FineCog-Nav](https://arxiv.org/html/2604.16298), Sec. 3.2/13 | Subgoals, completion assessment and action selection | Fixed action vocabulary, depth warnings | Strong UAV alternative; defer full eight-role replication and its call cost |
| [WMNav](https://arxiv.org/html/2503.02247), Sec. III | Direction values, subtasks and final actions | Six-view panoramas, curiosity map, geometry action proposer | Defer: changes sensors and adds candidate machinery |
| [STMR](https://arxiv.org/html/2410.08500) | Subgoal state and metric actions | External semantic segmentation and top-down metric representation | Defer extra perception stack |

MapGPT's author code confirms the previous-plan channel and simulator-supplied
viewpoints. FineCog's code confirms separate cognitive roles. Neither inspected
repository declares a license. Implement independently from published mechanisms;
do not copy their source or prompts. No new model weights or datasets are needed
for this development adaptation. Existing Gemma stays loaded; no cloud calls.

Source inventory: MapGPT commit 7c642f4507a8dde6703e2c61c8fd8ff3bc4bd322;
FineCog commit 9d2a6db04dd4262622d5697b63bb4a81922a498d. Inspected MapGPT
GPT/one_stage_prompt_manager.py and vln/gpt_agent.py; FineCog
src/common/cognitive_agent.py. Local primary-source caches are not redistributed.
WMNav project page links code; its executable code/license was not inspected.

## Exact source-to-adaptation boundary

| Component | Implemented design | Difference from source |
|---|---|---|
| Adaptive plan | One model call emits ordered subgoals, active ID and revised plan; previous plan is next input | Structured bounded JSON rather than MapGPT free-form plan over supplied node IDs |
| Memory | Model-authored scene summary plus bounded measured pose/action/outcome history | No supplied navigability graph, no full hierarchical FineCog memory |
| Completion/replanning | Model assesses ongoing/achieved/blocked/uncertain and chooses next subgoal | Assessment and expected-view fields inspired by FineCog; fused into one call, not eight-role replication |
| Action | VLM proposes normalized image point and travel label using existing SPF equations | Continuous UAV waypoint instead of Matterport node hop |
| Goal persistence | Explicit model retain action reissues the original world point | New runtime handoff adaptation: do not recompute an old pixel from a moved camera |
| Safety/execution | Existing SUPER, controller, shield and guarded monitor | Existing shared testbed execution; no assumption that visible space proves clearance |
| Sensors | Current forward RGB, pose and execution feedback; corrected depth remains available to shared stack | No panorama, oracle graph, truth target or semantic_hits |
| Backend | One Gemma e2b call per policy cycle, bounded output | Different model, cost and benchmark; published scores do not predict local success |

The scalar arrival distance is distance to the model's own commanded point,
not distance to the true mission target. Arrival does not automatically advance
the semantic plan. The VLM must decide whether its expected state was achieved.
The independent existing monitor retains terminal authority.

This also changes C5's depth-derived waypoint representation to SPF's model-named
travel. Therefore a later C5-versus-this flight is an end-to-end comparison, not
an isolated causal estimate of planning. Before a planning-only claim, use a
matched no-plan SPF control with the same action interface and execution settings.

## Coverage, stopping rule and falsification

Reuse the prior 41-candidate D-85 review and 24 meaningfully inspected primary
works; add three directly inspected planning methods (MapGPT, FineCog, WMNav),
and revisit STMR/SPF. The combined ledger contains 27 works, not 27 new reads.
Search trail and exclusions are in search_log.md. Stop broad search after the
primary method and official code confirm ownership and reveal adaptation costs.

Before any flight, fake-inference tests must prove that changing the model plan
changes the commanded subgoal/point; retained goals stay fixed across camera
motion; rejected decisions reach the next request; no automatic semantic
completion occurs; malformed output fails closed without mutating plan state;
reset clears memory; and prompts cannot acquire simulator goal/semantic hits.
All plan inputs and outputs must be accessible in debug capture and a reviewable
offline decision trace. No autonomous improvement is established by these tests.
No real calls, flights, cloud retries or held-out seeds are part of this phase.
