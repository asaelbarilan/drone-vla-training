# Search and inspection record

Date: 2026-09-10. Scope: protocol.md. Discovery combined the prior repository literature ledger, web searches using the protocol concepts, source-paper citations, author pages and official GitHub links. This is a reconstructed lane-level record, not a verbatim query transcript.

Search lanes: aerial pixel navigation (OnFly, SPF, Fly0); visual action proposals (PIVOT, VLMnav); structured grounding/maps (VLFM, VLMaps, LM-Nav, STMR); trained navigation and aerial benchmarks (NaVid, OpenFly, AerialVLN, CityNav, OpenUAV); spatial limitations (BlindTest, SpatialVLM, SpatialRGPT, NavBench); continuous embodiment (VLN-CE, MOKA, OpenVLA); recent memory methods (AirAnchor).

candidates.json records 41 screened entries; evidence.json records 24 retained primary works with targeted methods/results inspection. retrieval_log.json records the initial batch. VLMnav was additionally retrieved from https://arxiv.org/html/2411.05755 and cached in sources/vlmnav.txt. Unversioned URLs resolve to the version available at retrieval; the report distinguishes Fly0 v2 from its older public code.

resources.json records official repository metadata checks. Missing detected license does not prove absence of a license. SPF LICENSE was separately inspected and is proprietary. Fly0 tree and two source files were inspected and cached. The attempted PIVOT repository URL failed and remains unverified.

Local inspection covered the implementation lock, camera, task configuration, C5 verifier/policy, SUPER and controller yaw, and C1 observation serialization. replay_1061.json is an exact offline distance replay using the existing analyzer. No inference calls, new flights, held-out evaluations or credential-content reads occurred.

The evidence validator checks structure and coverage, not scientific truth or independent reproduction. Unverified resource facts remain marked in the ledger.
