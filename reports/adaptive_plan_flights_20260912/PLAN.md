# D-102: first adaptive-plan flight and dashboard diagnosis

User authorized flying the new architecture and debugging through the dashboard.
Start with one exact saved-frame local Gemma schema check, then one 90 s flight
on development seed 1061 using vlm_adaptive_plan_gemma_dev and corrected depth.
Keep task, Gemma weights, shared SUPER/controller/monitor and episode limit fixed.
Capture exact model requests, outputs, plans, source code and full motion events.
Compare with saved c5_depth_ray_v2_20260912_s1061, without claiming an isolated
planning effect (action representation and verifier differ).

Budget: one initial preflight; at most one additional preflight after a concrete
integration fix. At most two new 90 s flights, with the second justified by a
specific diagnosed defect or a prespecified reproduction need. No cloud calls,
model sweeps, held-out seeds, hidden retries or runtime parameter fishing.
If schema fails, repair the demonstrated integration defect before flight.

Watch the exported dashboard first: camera, observer/map, active VLM plan, action
point and motion at matching source times. Select first divergence, closest approach
and final/stalled interval. Then inspect the corresponding exact request/output,
routing and planner events. Separate observed failures from hypotheses. Preserve
failed runs, record changes in CHANGES.md and commit each cohesive change.
