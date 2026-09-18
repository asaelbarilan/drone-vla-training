# D145: openfly_vla on the same OpenFly data panel

User requested full dataset size and the released model beside the three trained adapters.

## Dataset size

At the pinned annotation revision: 100,226 training routes / 1,608,519 annotated decisions; seen evaluation 1,800 / 28,769; unseen evaluation 1,200 / 18,067. Total: 103,226 routes and 1,655,355 annotated decisions. Decisions can aggregate primitive steps; this is not a count of all raw images.

The official Hugging Face repository displays 2.97 TB (checked 2026-09-18). This includes repository representations and is not a deduplicated training storage requirement. Paper summary: about 100K trajectories across 18 scenes; the pinned training manifest has 11 environment IDs.

Sources: https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly and https://arxiv.org/abs/2502.18041. Exact local manifest hashes: dataset_size.json.

Our prepared joint dataset has 5,200 examples: 4,085 train / 1,115 validation. OpenFly contributes 2,929 / 815 across 88 / 22 routes; local contributes 1,156 / 300. Each pilot actually saw 592 unique OpenFly and 790 unique local examples, with 1,600 exposures per source.

## Matched observation results

| Model | Direction agreement | Exact next primitive | Valid native action | False STOP / 60 |
|---|---:|---:|---:|---:|
| smol256 | 18/72 | 18/72 | 72/72 | 9/60 |
| smol500 | 16/72 | 16/72 | 72/72 | 5/60 |
| qwen | 17/72 | 17/72 | 72/72 | 8/60 |
| openfly_vla | 18/72 | 8/72 | 59/72 | 2/60 |

The same 72 case IDs, route instructions and three causal images are used. Released openfly_vla uses NF4, its native processor and raw instruction with vlnv1 normalization from released eval.py; our models use their trained six-ID prompt. Raw tokens/vectors, loading checks and all image hashes are retained. Independent CPU decoding reproduces all 72 vectors. No unknown vector is converted to STOP.

Direction agreement credits forward 6m/9m when the target is forward 3m; exact primitive does not. openfly_vla requests forward 9m on 39 cases; 13 outputs do not match a released action codebook vector. The native vector value 2 for vertical motion is mapped by the released controller to the 3m primitive, not interpreted as a velocity.

These routes are official TRAIN: held out from our adapters, potentially seen by the released checkpoint. This is not an equal-unseen comparison. Raw-step versus macro-action/history conventions and 4-bit inference also limit interpretation. These numbers do not reproduce or disprove the published closed-loop benchmark. Local velocity-JSON exact matching is not defined for openfly_vla; no conversion or flights were added.

Browser audit checks all 72 cases / 288 raw answers, images, provenance, table rows and mobile layout. Existing three-model dashboard still passes all 300 final-answer checks. No new training, AWS spending, baseline/split changes or protected seed use.

Review: http://127.0.0.1:8771/openfly_same_panel.html
