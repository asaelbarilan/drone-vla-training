# Small VLAs for drone control — reading list

Gathered while answering: *is there a small VLA we can drop into the C7–C14
direct-action slot on an 8 GB laptop GPU?* Conclusion and ranked options in
[`docs/SMALL_VLA_SEARCH.md`](../../docs/SMALL_VLA_SEARCH.md).

One line each: what it is, and the one thing we took from it.

| file | what it is | what we took |
|---|---|---|
| `2026_LiteVLA-H_dual-rate-onboard-aerial-vla.pdf` | 256 M aerial VLA, dual-rate: 19.7 Hz action branch + 6.1 Hz semantic branch on one backbone, 2.2 GB on Jetson Orin | **The existence proof.** A 256 M model can hold aerial action authority at 20 Hz. Also independent confirmation of the C10–C13 dual-rate premise — and its K=3 scheduling with event-triggered override is almost exactly our `hybrid` scheduler. Weights not released. |
| `2025_GRaD-Nav++_onboard-vlm-drone-navigation.pdf` | lightweight VLA trained in a 3DGS simulator via differentiable RL; MoE policy, runs fully onboard | Precedent for **training the policy rather than downloading one**. 83 % sim / 67 % real on trained tasks. Code released, checkpoints not. |
| `2026_Exp2VLA_expert-distillation-drone-navigation.pdf` | distils Isaac Lab expert rollouts into a dataset, fine-tunes a compact VLA | The recipe for option 1: **expert distillation is the standard answer** to "no small aerial VLA exists", not a workaround. |
| `2026_AerialVLA_minimalist-end-to-end-uav-control.pdf` | 7 B OpenVLA fine-tune, continuous UAV velocity, 420 k frames / 7,922 trajectories | The LoRA on disk is for this. **17 GB VRAM, 0.38 s latency on a 4090** — the number that rules it out at bf16 and sets expectations at 4-bit. |
| `2025_CognitiveDrone_vla-benchmark-uav-reasoning.pdf` | 7 B VLA + 7 B VLM reasoner at 10 Hz / 2 Hz; 59.6 % → 77.2 % with the reasoner | The published version of our C10. The **+17.6 pt gain from adding a slow reasoner** is the effect size C8→C10 is trying to detect. |
| `2025_survey_efficient-vision-language-action-models.pdf` | survey of efficient VLAs: MiniVLA, TinyVLA, SmolVLA, quantisation, distillation | Confirms the field's small models are **all manipulation**. Read this before proposing any "just use a smaller VLA". |
| `2026_review_vla-for-uav-and-bimanual.pdf` | review across 183 works, 2017–2026, incl. UAV navigation and action representations | Taxonomy of aerial action representations; useful for choosing what our behaviour-cloned policy should output. |

## The negative result worth remembering

The obvious move — *take a small off-the-shelf VLA and point it at a drone* — is
not available, and the reason is structural rather than incidental: small VLAs
exist because manipulation datasets exist. Both drone-specific papers that solved
this (GRaD-Nav++, Exp2VLA) **generated their own expert data in simulation**
instead. We already have the simulator and a competent oracle, so that path is
cheaper for us than for either of them.
