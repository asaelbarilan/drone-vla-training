# D150: expert execution contract and original-source calibration

The three frozen D148 development routes pass kinematic reconstruction with the
corrected macro start frames. This establishes consistent coordinates and action
execution on those routes, not a successful policy or a simulated flight. A new
AirSim 18 source control also passes raw-action reconstruction and has a proven
vlnv20 decoder assignment. Renderer setup is the next gate; no new model inference
or training is included in D150.

## What now checks out

`openfly_execution.py` implements the released evaluator's native pose transition
and AirSim coordinate reflection. Forty comparisons against the isolated pure
function in upstream `train/eval.py` agree. Source revision:
`c075075497a7122bad82f5b76b9be926ad5a81b3`; exact file SHA is in
`expert_reconstruction.json`. No upstream launcher or cleanup function was run.

The eight-component output is a codebook, followed by an ID-to-pose adapter:
left/right vector value15 means a30-degree turn; up/down value2 means3 vertical
source units; lateral value5 means3 lateral units; forward3/6/9 retains that
displacement. These are not velocity vectors. AirSim uses metres; GS scale is not
calibrated here. Invalid codes raise errors and never silently become STOP.

| Frozen development route | Raw frames | Original annotation-frame mismatch, maximum | Corrected macro mismatch |
|---|---:|---:|---:|
| AirSim Guangzhou horizontal |22|6.000m|less than1e-6m|
| AirSim18 altitude |45|3.718m|less than1e-6m|
| GS SJTU campus |38|6.000source units|less than1e-6source units|

Every raw atomic pose also reconstructs to numerical precision for these routes.
This independently supports D147's macro-start-frame repair. No existing labels,
splits or results were rewritten. The original raw routes' exact RLDS membership
is still unresolved; this check alone does not assign them a decoder.

## Additional real defects and protocol distinctions

The Shanghai raw episode paired with vlnv11 contains `donw` with value0 at frame24,
followed by an observed3m descent. Strict reconstruction halts at that unknown
label. An explicitly labelled diagnostic interpretation as DOWN reproduces the
remaining motion, but is not adopted into training. Its terminal raw STOP also
carries scalar value3. Original packed labels and current raw observations differ:
the campus packed sequence deviates by up to8.728source units and Shanghai by
6.526m when integrated against their nearest matching current-release images.
Those image matches are approximate and do not establish byte-identical versions.

Inspection of the released evaluator identifies additional reasons not to compare
its headline metrics with our strict next-action score:

- `simSetVehiclePose(..., True)` performs pose placement with collision ignoring;
  it is kinematic rendered navigation, not a velocity-controlled dynamics test.
- Final distance below20 counts as success even after timeout or an image error;
  invalid codebook vectors also fall back to STOP in that source. Our adapter
  preserves an explicit invalid-output failure instead.
- Its SPL calculation divides straight-line start-goal distance by travelled
  distance without bounding the denominator. A30m goal and STOP after15m gives
  legacy success and an SPL-like value near2. We do not call this benchmark SPL.
- Its goal is the final stored pose, which can differ from mission STOP before
  descent; D147 quantified that mismatch across annotations.

The new diagnostic metrics record final distance, closest approach, path length,
explicit termination, strict STOP-at-goal success and legacy endpoint-only success
separately. They make no collision-safety or published-benchmark equivalence claim.
These are observations about released code, not proof of how every paper result
was generated. The public checkpoint-to-v7-paper correspondence remains unresolved.

## All20 public packed-data subsets checked

The previous saved repository tree contained only the first API page. Four pages
now cover3185entries and all20subsets at OpenFly-rlds revision
`aaf4a5288134d5386018392e7f1ce57bb40c4a9c`. Dataset metadata reports87,157 TRAIN
episodes and460,440,792,255bytes across those subsets. This count differs from the
100,226 current raw TRAIN annotations; it is a different released representation,
not a count of examples consumed by our adapters.

The sparse protobuf reader sampled each first shard's first episode identity,
transferring360,448range bytes rather than whole shards. All20 sampled identities
occur in current official TRAIN and not the3,000 official evaluation routes.
Header CRCs were checked; partial samples do not claim payload CRC verification.
Two sampled identities independently match the complete CRC-verified D148 records.
The complete stats and first-route identities are in `subset_identity_audit.json`.

Every source profile matches its checkpoint statistics. There are ten horizontal
profiles, nine vertical profiles, and one additional signature: **vlnv8 has actual
up/down maxima2 but q99=0 for both dimensions.** Encode/decode round-trip tests
cannot recover either vertical action under that profile. A regression now catches
this quantile-clipping failure. It does not explain mistakes in other subsets and
does not justify substituting a different profile by score.

Sampling environment identities is not an exact membership index. We have not
assigned the three old raw routes to shards using these samples.

## A source-matched route ready for the next renderer test

Before any new inference, froze the first episode of the first vlnv20 shard:
`env_airsim_18/astar_data/medium_long/2025-01-19_04-40-57_927964`.
It is absent from all110 routes used by our previous adapter pilot and from the
official evaluation set. It is an official TRAIN reproduction control, potentially
seen by OpenFly, not an equal-unseen generalization benchmark.

Downloaded one11,220,957-byte framed record, verified both CRCs and source stats,
and fetched its49,945,872-byte current raw Parquet at revision
`a12316d56a4e35a32ad626fb725ed7089937a1c4`. It has40packed steps and75raw frames.
Every raw expert pose reconstructs correctly. Packed/current image matches have
maximum MAE7.166/255 and packed integration mismatch6m. Two stored history slots
match future observations. Future images will not be used in new rollouts.
See `source_control_selection.json` and `source_control.json` for provenance.

## Local runtime and access

Inventory found an idle RTX4060 Laptop with8188MiB VRAM, about28GB free on C: and
956GB on D:. Ubuntu22.04 under WSL2 has WSLg and CUDA visibility. Added21 standard
Ubuntu graphics/audio libraries and diagnostic packages (15.8MBdownload,
66.0MBinstalled); no distro upgrade or signature-check bypass. A pre-existing ROS
repository has an expired signing key and was left unchanged.

At first the authenticated account received403 from OpenFly_DataGen. After the
user granted access, the same local authentication received206 for an exact range.
No credentials were displayed. The smallest matching env18 archive is285,821,005
bytes. The first whole-file response was incomplete; retry uses exact bounded
ranges and the authenticated LFS SHA256 before extraction. The retry finished with matching LFS SHA256 and ZIP CRC;377,676,858bytes were
extracted after path/symlink checks. Scene inventory and download status are separate artifacts. Graphics checks report OpenGL4.1 on the
Intel D3D12 adapter and software Vulkan/llvmpipe; actual rendering is not yet
validated in this decision. No cloud resources or new model jobs were started.

## Viewer and validation

Open <http://127.0.0.1:8771/openfly_execution.html>. Six routes,237recorded previews,
and452displayed diagnostic steps show expert labels, pose overlays, altitude,
unknown labels, STOP boundaries and exact source details. It is explicitly a
recorded-data reconstruction, never presented as a model-controlled flight.

33 focused unit tests pass, including invalid-output termination, coordinate
reflection, source normalization, sparse parsing, history and annotation guards.
All452 displayed steps, playback, buttons, route deep links and mobile overflow
checks pass in an isolated headless browser, with zero page or HTTP errors. The
desktop screenshot was visually inspected. The normal app automation tool failed
to initialize because of its Windows sandbox helper; no existing browser profile
was used for the headless tests. A hash-navigation defect found in this check was
fixed. Ruff and whitespace checks pass.

Reproduction scripts: `audit_openfly_execution.py`,
`audit_openfly_rlds_subsets.py`, `prepare_openfly_source_control.py`,
`build_openfly_execution_debugger.py`, `check_openfly_execution_debugger.py`.
The first metadata attempt failed to decompress some small JSON responses; its
partial results remain in `subset_identity_attempt1.json`. The successful audit
uses decoded bounded responses. The source-control Parquet first exceeded a32MiB
cap; its size was checked before raising that single-file cap to64MiB.

## Next gate

Finish local scene setup, render the verified expert route, compare camera/frame
conventions, then run bounded paired model-controlled navigation using new images
at each predicted pose. Keep renderer failure separate from model/control failure.
Do not infer real flight readiness or start more training from the checks above.
Preserve seeds1-40/1060-1064, all weights/baselines and frozen dataset indices.
