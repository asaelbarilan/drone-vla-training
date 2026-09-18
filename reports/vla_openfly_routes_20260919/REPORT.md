# D148: the previous global decoder repair was incomplete

The user's objection was justified: D147's single vertical-capable decoding profile
can turn valid horizontal predictions into invalid mixed actions. A coverage check
only proves that a profile can represent an action; it does not prove that the model
used that normalization for a particular training subset. D147's model ranking is
not validated and its profile must not become the universal OpenFly adapter.

## Direct evidence from the authors' packed training data

Downloaded only the first TFRecord episode of the first listed vlnv1 and vlnv11
shards. Length and payload CRC32C checks pass. Their source statistics match the
corresponding checkpoint statistics exactly, including min/max/quantiles and all
reported means/stds. Both route IDs are official TRAIN and absent from all 3,000
official evaluation routes. These are reproduction diagnostics, not held-out tests
of OpenFly. No examples were added to our training or validation sets.

| Original packed TRAIN episode | Decoder | Raw prompt: direction / exact macro | Training interface: direction / exact macro |
|---|---|---|---|
| Reconstructed NWPU campus, 15 steps | source-matched vlnv1 | 12/15 / 10/15 | 12/15 / 10/15 |
| Shanghai altitude route, 19 steps | source-matched vlnv11 | 7/19 / 6/19 | 10/19 / 9/19 |

All 34 outputs are valid with their source-matched decoder in each interface.
The training interface changes prompt and historical-feature pooling together;
its improvement on the altitude episode cannot be attributed to either alone.
The source training transform drops step zero; pipeline-kept counts are also
reported in summary.json: campus 11/14 directions, altitude 10/18 with training
interface. Repeated terminal observations remain visible rather than hidden.

**The same 15 campus token vectors decode to ZERO valid actions with vlnv11.**
In a horizontal subset, up/down dimensions have min=max=0, and training maps them
to normalized zero (token 31872). Interpreting that midpoint with a 0..2 vertical
range yields up=1 AND down=1. Those are decoder-created mixed vectors, not the
model issuing both commands. Conversely, horizontal decoding cannot recover
altitude commands. The codec now exposes a source-statistics check and a regression
test catches this exact failure even when the wrong profile passes action coverage.
No nearest-codebook projection, invalid-to-STOP fallback or score-based profile
selection was introduced.

## Three complete existing development routes

Before inference, chose the lowest SHA256 route identity in three categories,
requiring a complete motion-verified route: AirSim horizontal, AirSim vertical,
and GS horizontal. All 105 raw frames and all 43 macro decisions are retained.
Four OpenFly interface variants produce 172 calls; two packed records times three
interfaces produce 102 calls. The unchanged Qwen adapter adds 43 calls. No training.

| Route | Same OpenFly tokens, vlnv1 direction | Same tokens, vlnv11 direction | Qwen direction | Always-forward reference |
|---|---:|---:|---:|---:|
| AirSim horizontal | 7/9 | 0/9 (all invalid) | 2/9 | 7/9 |
| AirSim altitude | 11/18 | 11/18 | 7/18 | 14/18 |
| GS campus | 11/16 | 0/16 (all invalid) | 1/16 | 12/16 |

These raw routes' historical normalization assignments are not yet traced to their
exact packed shards. Both decoder views are therefore reported as a calibration
sensitivity test; do not select whichever profile scores better. The two original
packed episodes above have stronger, source-matched calibration evidence. Qwen's
10/43 does not establish a universal ranking either. Natural route frequencies
include 33/43 forward labels; high direction agreement alone is easy to obtain.

Native resizing changes the vlnv11 aggregate 11/43 to 12/43; causal transition
history gives 11/43; training prompt/pooling plus that history gives 12/43. All
four have exactly 25 invalid horizontal cases under the vertical profile. The
calibration error dominates these interface controls. Prior six-case BF16/NF4
identity from D147 still weakens quantization as a sole explanation, without
establishing full precision equivalence.

## Confirmed defects and version differences in actual training records

Both downloaded episodes contain future images in their stored history, verified
by identical encoded-image SHA256 hashes to later current observations. Campus
step1 receives terminal images12/13/14; altitude step1 receives16/17/18 and steps2
and3 receive frame4. These four affected steps survive the training transform's
first-step removal. This confirms the released builder's future-reference problem
in actual artifacts, rather than only in unused example code.

**Removing only those future images changes no generated tokens on either sampled
episode.** It is a real data defect, but not the demonstrated cause of these
predictions. We neither adopt the leakage for new training nor infer its prevalence
from two episodes. Exact stored inputs are labelled contaminated reproduction
controls in the debugger; separate causal inputs replace future frames.

Current public annotations and packed training data also differ. For these two
routes, every annotated forward6m is encoded as forward3m in the packed record
(one campus instance, two altitude instances). Packed altitude phase tags are
ordinary up/down vectors; current annotation uses -1/-2. Each packed episode adds
two duplicate final STOP entries, and the altitude instruction has different
landmark descriptions. Thus “same public dataset” is not “identical training
representation.” Neither version was silently rewritten.

The corresponding two raw Parquets were downloaded with 32MiB/file caps. Closest
image matches under four standard resize kernels align packed current observations
with the annotated raw-frame IDs (including compressed block endpoints). Their
maximum pixel MAEs are 2.41 and 3.54 out of255, so these are close visual matches,
not byte-identical cross-version images. The future-history finding above uses
exact within-record hashes and does not depend on this approximate matching.

## What the paper measured

The [paper, Table1 and section6.1](https://arxiv.org/html/2502.18041v6#S6) reports
flight SR33.2% seen/10.7% unseen and oracle SR63.5%/48.9%, with a20m goal radius.
Those measure whole trajectories, not exact next-action agreement. Table2 reports
12.7% SR with ordinary history and33.2% with the full method. Our causal transition
sampler does not recreate the paper's landmark filter/token merging.

## Visual evidence and actual remaining errors

Open localhost8771/openfly_routes.html. It replays every raw camera frame for the
three routes, marks the actual decision frame, shows three exact input previews,
recorded and predicted commands, raw tokens/vectors, and one-step pose/heading
arrows. Camera motion is the recorded route; predictions do NOT drive the replay.
Packed episodes are available in the same selector with future-history warnings.
GS axes/altitude are labelled source units; metric calibration remains unverified.

For the packed campus example, OpenFly predicts forward9m at step1 where the
recorded action is a right turn; it predicts left a step early at step2. Near the
end it chooses forward3m instead of9m, then STOP one observation before the label.
The last two are different issues from a wrong turn and need actual closed-loop
assessment. The altitude example still fails its initial climb in the training
interface. Correct decoding does not make this a solved navigation policy.

## Changes, limits and next gate

The source-statistics guard and causal-history tests are implemented. All existing
weights, splits, index files, baselines and protected seeds1-40/1060-1064 are
preserved. Original outputs remain immutable; counterfactual decoding is explicit.
All model jobs ended. No cloud resource, paid training or physical drone was used.

Next bind raw route/domain identifiers to their actual RLDS subsets, keep a single
explicit action contract for our future data, and test a small source-faithful
closed-loop rollout with real rerendered observations. Stop relying on the old
balanced table as evidence that Qwen equals or beats OpenFly. Do not claim that all
remaining policy errors are explained or that this reproduces the paper benchmark.

Reproduce with inspect_openfly_rlds_records.py, prepare_openfly_route_diagnostics.py,
prepare_openfly_rlds_diagnostics.py, evaluate_openfly_routes.py,
evaluate_qwen_openfly_routes.py, audit_openfly_packed_versions.py,
audit_openfly_route_calibration.py and build_openfly_route_debugger.py.
The first inference invocation ended before any prediction because the source
statistics check initially compared the added checkpoint mask against a source
without that field; after comparing numeric fields and validating the default
all-true mask, a fresh output directory was used. No failed run was scored.

Validation:13 focused tests pass; ruff and git diff whitespace checks pass. Browser checks all139 source frames,360 displayed prediction/decoder entries, exact triplets, playback, deep links and mobile layout with zero console/HTTP errors. The packed campus and raw AirSim route views were visually inspected.
