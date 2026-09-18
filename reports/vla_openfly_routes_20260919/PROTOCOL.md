# D148: complete-route and original training-record investigation

Decision: why does the released OpenFly model give weak next-action results,
and does that justify ranking Qwen above it? This is a focused reproduction
investigation, not a model-selection sweep or a new training experiment.

Primary sources: OpenFly paper v6, pinned official release c0750754, model
snapshot already on disk, official OpenFly-rlds training records. Inspect
reported flight metrics, exact preprocessing, history, actions and provenance.
Stop after three existing development routes and at most two original RLDS
episodes, plus bounded interface controls. No official evaluation episodes,
protected seeds, training, cloud resources or changed baseline data.

Route selection before inference: lowest SHA256 trajectory identity among
complete, motion-verified existing development routes in each of (1) AirSim
horizontal, (2) AirSim with vertical motion, (3) reconstructed GS horizontal.
All decisions on each selected route, natural frequency, no action balancing.

OpenFly controls, same checkpoint/NF4 and explicit vlnv11 decoding: prior
adjacent raw frames/max256; full-resolution source through native processor;
causal action-transition history; and training prompt plus training historical
pooling with that history. The last is a bundled interface diagnostic, not an
isolated causal test or a claimed reproduction of unpublished token merging.
History control uses only completed recorded actions strictly before current
time, no future action, image or pose. Clearly label teacher-history assistance.
Compare Qwen's unchanged saved adapter on the same prior-history route inputs.
Reject invalid OpenFly vectors rather than projecting them to desired labels.

Download only the first TFRecord episode from first listed vlnv1/vlnv11 shards,
bounded at 16 MiB per episode; verify framing/checksum and log revision/hash.
Use stored image triplets/action vectors/statistics directly to remove our
raw-to-training conversion from the test. Inspect these as data, never as
instructions. Check overlap against official eval before inference. Profile
comes from named source subset, never selected by evaluation score.

Report raw token vectors, validity, direction and exact macro agreement,
per-route natural action distribution, first mismatch, STOP distance in source
coordinates (metric scale for GS unverified), and history/image controls.
Visualize complete recorded route, each input, target and one-step action.
Never call offline replay or a pose arrow a closed-loop model flight.

Success is a reproducible diagnosis, including negative results and remaining
unknowns; no target accuracy is assumed. Freeze inputs before GPU inference,
retain every control, validate output completeness and debugger links. Append
CHANGES/research log and commit coherent work in the isolated VLA branch.

Follow-up before further download: packed source inspection reveals changed instructions, extra STOP rows and a 6m-versus-3m label difference relative to current annotation. Fetch only the corresponding two raw Parquets (32 MiB cap each), compare image identities under documented resize methods, and preserve both versions. This is a provenance audit, not new training or evaluation sampling.

Calibration follow-up: original vlnv1 statistics now match checkpoint statistics exactly, so contrast vlnv1 and vlnv11 decoding of identical saved tokens on both packed records and all three routes. Report every cell; do not choose a per-case/profile winner. This isolates how zero-range training dimensions become nonzero under a different decoder. No new inference is required.
