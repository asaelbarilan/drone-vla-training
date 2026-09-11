# C5 navigation implementation and literature audit

Decision question: Does failure on the basic red-tower navigation task implicate the VLM, the local implementation, a transfer mismatch, or the architecture family? What minimal experiment distinguishes them without changing the task?

Scope: published and public work through 2026-09-10; primary full papers and official resources. Prioritize OnFly, See-Point-Fly, OpenFly, aerial VLN, zero-shot ground navigation, robot VLM interfaces, spatial failure analyses, benchmark task/observation fairness. Keep the existing task and frozen SUPER substrate. No model API calls, no held-out seeds, no secret inspection, no policy modifications during review.

Search concepts: OnFly UAV dual-rate VLM monitoring memory; aerial vision-language navigation pixel waypoint depth camera calibration; zero-shot object navigation affordance visual prompting; VLM spatial grounding failure; simulation domain shift; asynchronous stale waypoint control. Sources: arXiv, conference proceedings, author project pages and official GitHub. Seek both claimed success and failure, code and unpublished implementation gaps. Backward/forward citation follow-up from direct solutions.

Inclusion: navigation or embodied VLM systems with identifiable observation/action interface; evaluations or failure analyses relevant to grounding, execution or stopping. Exclusion: generic chatbot benchmarks without spatial relevance, pure image generation, unsupported marketing. Screen >=30 candidates; retain >=20 meaningfully inspected works, including >=3 direct solutions and >=3 benchmarks. Stop after core claims, contradictions and resource gaps are supported; do not manufacture missing results/resources. Missing resource facts remain not_reported or not_verified.

Acceptance: source-to-code discrepancy matrix; ledger with exact supported claims and inspection depth; distinguish demonstrated evidence from hypotheses; bounded tests that would falsify each leading explanation; paper claims restricted to actually tested configurations. Markdown report and JSON evidence ledger, validated with the skill validator.
