# AeroVLA evidence review

Search/inspection date: 2026-08-25.

## Decision

AeroVLA is the correct C7/C8 representative because its causal boundary is
unambiguous: a single foundation model maps current pixels and language
directly to a kinematic displacement and terminal action. It therefore tests
the intended question—whether waypoint planning can be removed—without
quietly retaining a waypoint decoder, object detector or high-level planner.

The official release materially changes the old project assessment. Code,
training data and a 463 MB LoRA now exist. The remaining native constraint is
the 15.1 GB OpenVLA-7B base and the paper's reported 17 GB inference footprint,
which exceeds this machine's 8 GB GPU. The native profile must still be wired
and fail clearly; it cannot be silently replaced by the old scripted `mock_vla`.

## Mechanism extracted from primary sources

| Element | Paper and released source | Testbed decision |
|---|---|---|
| Visual input | Front and down RGB, vertical mosaic, 224 x 224 | Add an adapter-neutral down-RGB sensor reference and share one mosaic function |
| Language | Target description plus seven-way fuzzy relative bearing | Add a bucket-valued sensor prior only to declared coordinate-prior navigation regimes |
| State | Current observation only | No memory consumption in the AeroVLA profile |
| Output | Three 0-98 standard numerical tokens | Strict typed codec; malformed output fails closed |
| Physical command | Forward/vertical/yaw spatial offsets, executed at 1 m/s | Body-relative offset becomes ENU `KinematicAction`; no planner |
| Stop | `LAND` or near-zero offsets | Emit `MissionDirective(STOP)` only from that dual condition |
| Safety | No independent shield in the base system | C7 is bare; C8 adds only the common independent shield |

## Source discrepancy retained rather than guessed away

The paper states yaw de-quantization over `[-pi, pi]`, while both the released
dataset and inference wrapper use `[-1.1, 1.1]` radians. The executable release
is used for the implementation profile, and the discrepancy is logged in model
provenance. This is preferable to inventing a third range.

## Falsification risks

- The model's coarse bearing requires a known target-location prior. It cannot
  be supplied in unknown-location semantic search without changing the task.
- Paper results use a 20 m success radius; the local benchmark requires 2 m and
  an explicit terminal decision, so published success does not predict a pass.
- Native BF16 is hardware-infeasible locally; quantized inference may change
  action tokens and must be labeled as such.
- The flat-shaded local simulator is far outside TravelUAV's image domain.
- A Gemma-backed normalized profile tests the architecture interface, not the
  released AeroVLA policy's learned competence.

These limitations are acceptance tests, not reasons to reintroduce scripted
steering or oracle stopping.
