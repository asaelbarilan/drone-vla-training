# Gemma Windows visual-runtime repair

The same Gemma 4 E2B weights now recognize the previously missed target.
Navigation is still under evaluation; the first unchanged-policy flight
exposed a premature stop at 14.356 m.

## Before/after controls

| Exact source frame | Original package | Repaired package |
|---|---|---|
| Close red rectangle, seed 1061 / observation 1560 | absent | red rectangle visible |
| Distant red target at left, seed 1061 / observation 480 | absent | red object on left |
| No visible target, seed 1061 / observation 1 | not part of original paired probe | absent |

The full navigation prompt also changed its distant-frame output from the
image center to a leftward point. This is evidence of restored visual input,
not a guarantee of precise localization or successful navigation.

## Repair

Ollama v0.33.3 promotes the unified Gemma patch embedding to F32 on Windows.
The [upstream fix](https://github.com/ollama/ollama/pull/16879) restricts that
conversion to Apple. The local workaround extracts a clip/gemma4v projector
with original F16 patch weights and the corresponding metadata. The combined
package includes the original audio tensors with upstream compatibility
renames. Audio task quality has not been evaluated.

- Language layer unchanged: `4e30e2665218745ef463f722c0bf86be0cab6ee676320f1cfadf91e989107448`.
- All 1,411 multimodal tensors have verified unchanged bytes, dimensions and types.
- Projector: `e0a8a3ffbd3731d8cdbf7bedbdce4268ec72f8488fbe27a63c65e1dc7b7f450a`.
- Shared tag remains `gemma4:e2b`; new package digest:
  `6fbe8a5f242b4bf980850341db5efac369ad2b0d142fde673d7e0fe2a911c8aa`.
- Original package retained as `gemma4:e2b-before-projector-fix-20260907`.
- No Ollama server restart. `/api/ps` confirms one resident package. It may
  display the temporary `e2b-mmfix-dev` name that first loaded those same files.

## Reproduce and roll back

`gguf==0.19.0` is installed only in the ignored workspace staging directory.
`scripts/stage_gemma_vision_projector.py SOURCE OUTPUT --include-audio` stages
and verifies the projector without modifying the source. The local Modelfile
is under `tmp/gemma_runtime_repair/Modelfile.multimodal`.

If rollback becomes necessary, copy the saved tag back with
`ollama cp gemma4:e2b-before-projector-fix-20260907 gemma4:e2b`, then select the
old development profile with its original digest. Do not interrupt an active
shared inference job. Historical configs retain original digest pins.

## Navigation gate

The active baseline profile uses the repaired runtime. The separate
`c5_gemma4_e2b_runtime_fixed_target_stop_dev` tests target-bound arrival on
1060–1064. Its runner is `tmp/run_gemma_fixed_target_stop_20260907.py`; results
accumulate in `GEMMA_RUNTIME_FIXED_TARGET_STOP_GATE_20260907.json`. Inspect
current process/result state before resuming; never overwrite existing runs.
288 unit/contract tests pass. No held-out evaluation has been run.
