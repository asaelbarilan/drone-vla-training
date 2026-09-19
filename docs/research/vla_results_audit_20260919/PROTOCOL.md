# Drone VLA review protocol and search log

Date:2026-09-19. Decision: does published aerial-VLA evidence explain the mismatch between our action-level OpenFly comparison and the expectation of a well-trained drone policy?

## Scope and acceptance

The user clarified **drone VLAs, not general robot VLAs**, after the initial general-robotics search. That initial scope is superseded; no manipulation-only model is counted or used to rank drone policies. Review15 aerial learned-action architecture papers, with supporting aerial benchmarks and explicit boundary cases. This is a user-narrowed application of the evidence-first-research skill; it does not authorize architecture changes or training.

Include primary papers with aerial agents, language+visual conditioning, learned action/waypoint generation, and inspectable methods/results. Retain both narrow velocity/body-rate policies and long-horizon waypoint policies, clearly separated. Exclude pure mission planning, training-free VLM+planner systems and dataset-only works from the15 architecture count. Keep benchmark evidence separately. Screen at least30 candidates; stop after15 architecture methods/results reviews plus supporting benchmark/resource checks. Unknown releases and protocols remain explicit.

Search range2023–2026, with older/foundational aerial benchmarks used through citation following. Search date2026-09-19; pinned PDF revisions and hashes stored. Primary sources: arXiv full text, AAAI publisher PDFs, author project sites, official GitHub/Hugging Face resources. Secondary lists are discovery leads only.

## Search lanes and queries

1. Direct aerial action policies: `drone VLA`, `aerial vision language action`, `OpenFly`, `CognitiveDrone`, `RaceVLA`, `AutoFly`, `AerialVLA`.
2. Memory and geometric action generation: `LongFly`, `SpatialFly`, `VLA-AN`, `FSD-VLN`, `FLIGHTVLA`.
3. World/action models: `WorldVLN`, `ImagineUAV`; inspect cited UAV-Flow and IndoorUAV protocols.
4. Small policies and real deployment: `Exp2VLA`, `GRaD-Nav++`, `SINGER`, `LiteVLA-H`.
5. Other task categories: `UAV-Track VLA`, `CosFly-Track`, `HUGE-Bench`, `AIR-VLA+`.
6. Boundary alternatives: `OnFly`, `See Point Fly`, `Fly0`, `UAV-VLA`, `VLFly`.
7. Release searches: paper name plus `github`, `code`, `weights`, `model`; follow only author-linked projects when available. Search results with homonymous GitHub usernames were rejected. An incorrect OpenFly repository lead returned404; official model card resolves the project to SHAILAB-IPEC/OpenFly-Platform.

Citation following connected OpenFly to AerialVLN/TravelUAV and FSD-VLN; WorldVLN and ImagineUAV to UAV-Flow/IndoorUAV; GRaD-Nav++ to RaceVLA/CognitiveDrone. Discovery expanded to31 aerial candidates. The AerialVLA dialogue publisher PDF was inspected via the web tool after direct Python download failed. It remains a boundary case, not padding in the15.

## Extraction and checks

Read each included paper's methods, experimental protocol and result table/figure. Record action representation, input/history access, benchmark adaptation, split, success definition, simulation versus hardware, supporting controller/planner, reported training/inference hardware, and limitations. Distinguish absent/not located information from a verified negative. Do not copy abstract improvements in place of actual result tables.

Inspect public metadata/READMEs for code, data, weight files and license declarations. No model or bulk data downloads. Resource audit is not license advice or proof of runnable reproduction. Capture inaccessible endpoints and missing declarations.

Corrections identified: OpenFly latestv7 differs from earlier localv6 citation; IndoorUAV heading tolerance is pi/4 rather than4degrees; Exp2VLA has problematic bibliography IDs and success/denominator ambiguities; GRaD-Nav++ has a simulation denominator/caption mismatch. These qualifications are retained rather than silently harmonized.

## Output and non-interference

Deliver15-paper table,19-row evidence ledger,31-candidate ledger, source manifest, resource inventory, mechanism taxonomy, experiment implications and falsification tests. Run structural validator with minimum15. Preserve all existing experiment results, weights and evaluation splits. Do not develop on seeds1–40 or1060–1064. Append D149 to CHANGES/research log, update handoff, commit only coherent research artifacts. No GPU runs or cloud spending.
