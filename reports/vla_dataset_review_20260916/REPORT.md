# Current VLA data: inspection before training

This is a pipeline-development corpus, not a validated deployment dataset.

- Source: local grid_nav_aerovla simulator, C0 privileged expert.
- 100 retained successful episodes, seeds 1200-1299; original 80/20 scene split.
- 4,765 RGB mosaics, front above downward camera, 224x224; saved every 0.5 s.
- 3,744 training / 1,021 validation samples; one repeated red-tower instruction.
- Actions: 99-bin forward displacement, down displacement and clockwise yaw,
  plus LAND. Labels were converted from expert controls, not recorded raw controls.
- 65 LAND labels; 35 episodes have none. Terminal visual grounding is unverified.
- Coarse goal-direction input uses the simulator's known goal position.
- No real-flight recordings, live sensor stream or external-simulator data in this set.

Structural validation is not action correctness. See the D-124 codec
counterexamples: zero expert motion becomes forward motion; speed/duration and
large yaw differ after conversion. Changing the codec alone does not certify
that labels are observable from the student's inputs.

## Playback

Open http://127.0.0.1:8771/viewer.html while the dedicated local server runs,
or open generated viewer.html directly in a browser. Select an episode, use
Play/Previous/Next or the timeline, and inspect exact source prompts and targets.
All original JPEG bytes are embedded without re-rendering or interpolation.

This is recorded camera playback. Original full pose/control logs were not saved
by the collector, so there is no defensible original 3D trajectory to display.
Fresh simulation reproduction must be identified separately and matched to saved
source images before claiming it reproduces a dataset flight. LAND is a mission
termination symbol in this corpus, not evidence of physical landing.

## Reproduce

Run from the isolated worktree with PYTHONPATH=src:

```powershell
python scripts/build_vla_dataset_viewer.py --source ../uav_arch_lab/data/qwen_vla_sft --out reports/vla_dataset_review_20260916
python -m http.server 8771 --bind 127.0.0.1 --directory reports/vla_dataset_review_20260916
python scripts/check_vla_dataset_viewer.py
```

SUMMARY.json records source/index hashes, episode coverage and structural audit.
UI_CHECK.json records exact selected source/label/timestamp comparisons, split
counts and playback checks. preview.png is the inspected browser capture.
No model inference, training or fresh simulation was used.

## Why QLoRA remains provisional

[QLoRA](https://arxiv.org/abs/2305.14314) trains low-rank adapters through a frozen
4-bit backbone to reduce memory requirements. That motivates a local 8 GB trial;
it does not certify fit, control quality or visual-domain transfer. BF16 LoRA
and selective vision adaptation remain options if memory and measured errors
justify them. The current cached AWQ inference artifact is not the NF4 base
required by the documented recipe.

A small synthetic overfit validates only that test's pipeline. It does not
validate Qwen adapter training or establish a language-conditioned flight policy.
Prioritize raw control/observation provenance and task/domain coverage first.

