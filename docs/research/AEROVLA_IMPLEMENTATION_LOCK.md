# AeroVLA implementation lock

Locked: 2026-08-25, before C7/C8 implementation or development episodes.

## Evidence and resource identity

- Primary paper: Xu et al., *AeroVLA: A Vision-Language-Action Model for UAV
  Navigation via Minimalist End-to-End Control*, arXiv:2603.14363v1, accepted
  to ECCV 2026.
- Official source: `XuPeng23/AeroVLA`, commit
  `e37685afb8953d1f5a09155d7255960cee1bfd9d`.
- Official adapter: `XuPeng23/AerialVLA/aero_vla`, 463 MB, Apache-2.0.
- Required base: `openvla/openvla-7b`, 15.1 GB, MIT.
- Official training JSON: 257 MB. TravelUAV imagery and AirSim environments are
  separate resources and are not copied into the normalized local simulator.

The broader 31-work evidence ledger remains
`docs/research/spf_evidence.json`; its AeroVLA row is updated with the complete
paper/resource audit and the ledger must continue to pass the evidence
validator.

## Paper-defining mechanism

1. A current front RGB view and current downward RGB view are vertically
   concatenated and resized to one 224 x 224 image.
2. The prompt contains that image, the target description and exactly one
   coarse target-relative bearing bucket: straight ahead, forward-left/right,
   left/right, or left/right rear.
3. The policy is reactive: no temporal history, external object detector,
   waypoint planner or semantic monitor participates.
4. One model call emits three integer bins in `[0, 98]`, deterministically
   decoded to forward displacement `[0, 5]` m, vertical displacement `[-5, 5]`
   m and yaw change. The released implementation uses `[-1.1, 1.1]` rad for
   yaw, which is the executable source-of-truth despite the paper text stating
   `[-pi, pi]`.
5. The decoded spatial offset is executed at constant 1 m/s. In the testbed it
   becomes one typed `KinematicAction`; it must never traverse SUPER or another
   waypoint planner.
6. `LAND` or a near-zero three-axis offset is the policy's intrinsic terminal
   decision. No detector, depth-range stop or environment success truth may
   trigger it.

## Profiles and honest normalization

One `aerovla` policy plugin supports two model backends; the geometry, prompt,
token codec and typed action path are shared.

- **Native resource profile:** official OpenVLA-7B plus official LoRA. It fails
  closed when either resource or the required inference runtime is absent. The
  paper reports 17 GB VRAM; native BF16 cannot run on this laptop's 8 GB GPU.
  A 4-bit experiment is permitted but is not claimed to reproduce the paper's
  native precision.
- **Normalized local profile:** Gemma 3 4B through the existing deterministic
  Ollama boundary, using the same dual-view prompt, three-bin action contract
  and intrinsic stop. This is an architecture-mechanism adaptation, not an
  AeroVLA checkpoint replication. It may satisfy the local family capability
  gate only if its model-authored direct actions actually complete missions.

The deterministic adapter gains two ordinary sensor fields: a downward RGB
reference and a coarse goal-bearing bucket. The latter is enabled only in
navigation regimes that declare a target-location prior. It is absent in
unknown-location object search. Policies receive only the bucket, never the
goal coordinate or exact bearing.

## Development gate

Held-out seeds 1-40 remain untouched. Use AeroVLA development seeds 1060-1064.

- Contract tests: exact 99-bin codec, source-faithful yaw range, strict parser,
  front/down mosaic order, seven bearing buckets, ENU action transform,
  intrinsic LAND, and explicit failure on malformed/missing model resources.
- Architectural guard: C7 has no planner or shield; C8 is the identical policy
  plus the common shield. Neither may read `semantic_hits`, depth, memory,
  `privileged`, a target coordinate or scoring status.
- Capability: at least 4/5 `grid_nav` successes for shielded C8 on seeds
  1060-1064, zero collisions, no parse errors/fallbacks, and every successful
  stop authored by LAND/near-zero output. Bare C7 is run on the same seeds to
  measure rather than pre-assume the shield effect.
- Determinism: repeated seed 1060 agrees on termination, ordered decoded model
  outputs and final distance within 0.25 m.
- Full focused tests, configuration validation, Ruff and regression pass.

The paper's published 20 m success radius is not imported. This benchmark's
2 m radius and terminal-stop requirement remain common and intentionally much
stricter. Failure under that normalization is a result, not permission to add
detector- or truth-based stopping.
