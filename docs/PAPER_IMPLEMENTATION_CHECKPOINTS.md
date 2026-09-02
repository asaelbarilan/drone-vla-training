# Paper implementation checkpoints

This is the compact sequential ledger for the eight-paper implementation goal.
Detailed decisions remain in `RESEARCH_LOG.md`; fidelity contracts and gates
remain under `docs/fidelity/`.

| Order | System | Testbed placement | Status | Evidence |
|---:|---|---|---|---|
| 1 | SUPER | shared planner/execution substrate for C0-C6 | **accepted, frozen** | corrective revalidation: 40/40 dev episodes, 0 collisions, 0 shield interventions; 280-test regression passes |
| 2 | AerialClaw | C1 skill/tool authority | **accepted, frozen** | real `gpt-oss:20b`; grid 5/5, object search 5/5, 0 collisions; deterministic repeat and 280-test regression pass |
| 3 | See, Point, Fly | C2 waypoint authority | **blocked on capable VLM; not accepted** | 31-work evidence review; clean-room RGB `point+distance` plugin; 296-test regression; five local backends rejected, including Gemma 3 4B/12B; Qwen3-VL 8B reaches but does not stop |
| 4 | AeroVLA | C7/C8 direct action | **mechanism integrated; not accepted** | Official profile fails closed without the 15.1 GB base/17 GB VRAM; Gemma profile emitted neutral `(49,49,49)` for all 19 calls on dev seed 1060 |
| 5 | OnFly | C3-C5 verifier/monitor/memory mutations | **mechanism works; development gate open** | Shared Qwen3-VL 4B seed 1061 succeeds with correct stop at 0.65 m, one recovery, 0 collisions/errors; seed 1060 remains a never-observed-target search failure, so C5 is not yet accepted |
| 6 | PMR / Selective Agentic Recovery | C6 event-triggered recovery | **in progress** | 18D learned-CVI/guard contract plus real typed GPT-OSS recovery are integrated; repeated 3/3 static semantic probes pass identically; 356-test regression passes; paired utility collection and checkpoint fitting remain |
| 7 | CognitiveDrone-R1 | C10 slow-reasoner/direct executor hierarchy | pending | — |
| 8 | FLIGHT | C11/C12 chunked and asynchronous hierarchy | pending | — |

SUPER and AerialClaw checkpoint date: 2026-08-25. Held-out seeds 1-40 were not
used.
