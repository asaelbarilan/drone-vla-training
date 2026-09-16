# VLA AWS pilot: recovery and preflight

Status: local preflight complete; remote inventory and GPU training blocked by
unavailable console/SSH access. User requests approval of the exact machine
before launch and again before training; no spending amount is approved.
Branch: `codex/vla-aws-pilot-20260916`, forked from `6be9a55`.

## Bounded research protocol

The user requested starting with the existing plan and hardware inventory,
without broad sweeps. Reuse the existing 31-work `spf_evidence.json`, the
primary-source drone survey, and the AeroVLA implementation lock. This is a
targeted resource/contract revalidation, not a new systematic review or a claim
that the old resource inventory is current.

Decision question: can the existing Qwen3-VL 4B SFT path support a small,
auditable direct-action pilot under the current nine-condition/eight-regime
paper design, and what blocks real/simulator transfer?

Search date: 2026-09-16. Scope: original papers, official code, model cards,
dataset metadata and official cloud pricing. Terms: AeroVLA/AerialVLA,
Qwen3-VL fine-tuning, UAV-Flow pose timestamps, OpenFly discrete actions,
Exp2VLA normalized actions, drone/kinematic velocity, AWS GPU pricing.
Inspect the existing historical evidence and current resources; follow primary
links only. Include resources with identifiable observation/action semantics;
exclude manipulation checkpoints as drop-in drone controllers. Stop once the
existing candidate and major external-data routes have explicit compatibility
gaps and availability evidence. Do not download large weights/data or select a
different backbone before hardware, semantics and spending gates are known.

## Frozen scope

Latest design: `ASP-UAV_Final_Research_Design.pdf` and
`general_single_uav_autonomy_benchmark_design.pdf`, read from the external
design directory named in `docs/CAPABILITY_SCENARIOS.md`.

The paper uses C0/C1/C2/C8/C3/C5/C6/C10/C12. C8 is the shielded direct-action
base; C7 remains the unshielded ablation. Keep one executor checkpoint across
direct/hierarchical variants. Report training regime separately from authority
and supervision; trained VLA versus frozen VLM is not an isolated architecture
effect. Keep shared dynamics, observation access, controller, shield, timeouts,
and latency accounting frozen. No held-out seeds 1-40. Do not train on the
development evaluation seeds 1060-1064 for this new pilot.

## Initial recovered state

- Existing recipe: Qwen3-VL 4B Instruct, NF4 QLoRA, rank 8, frozen vision/aligner,
  batch 1, accumulation 16, three epochs. SFT before optional DAgger, no initial RL.
- Existing collector: privileged C0 labels; student front/down RGB mosaic,
  instruction and declared coarse bearing; strict 99-bin forward/down/yaw + LAND.
- Existing main dataset: 100 successful episodes (1200-1299), 4,765 samples,
  3,744 train / 1,021 validation; 65 LAND labels. It does not meet the old
  10,000-sample gate and does not cover eight task categories.
- Existing small convnet BC/DAgger checkpoints are visuomotor policies without
  language input, not a trained Qwen VLA.
- No locally discoverable AWS CLI, AWS config/profile or SSH host config.
  SSH executable exists. Key contents were not read. Remote inventory remains
  unknown, not inferred from the laptop.
- Laptop only: RTX 4060 Laptop, 8,188 MiB total VRAM; about 20.8 GiB disk free at
  inspection; torch 2.6.0+cu124, transformers 4.44.2, no peft/bitsandbytes/ms-swift.

## Open contract risks to measure before training

1. Absolute Windows paths in ms-swift exports are not portable to Linux.
2. Existing validation checks counts but not one-to-one ms-swift image coverage,
   prompt equality with deployment, or image decoding.
3. The privileged C0 velocity-to-offset teacher conversion is lossy: yaw clips,
   speed changes in the decoder, and zero-velocity nonterminal labels become
   forward motion. Measure this rather than calling it quantization noise.
4. LAND labels are based on geometric radius, while the prompt requires a red
   target centered in the downward view. Audit label observability.
5. The reactive bearing-prior profile cannot implement unknown-location search,
   general multi-stage memory, or a true hover. Preserve its native profile;
   any broader input/action interface must be a separately named adaptation.
6. Flat-shaded, single-instruction synthetic data cannot establish real-world
   or cross-simulator competence regardless of adjacent frame count.

## Completed local audit

`reports/vla_aws_pilot_20260916/source_audit.json` validates every indexed image,
strict target, annotation and split. All 4,765 images decode as 224x224 RGB,
13,944,148 image bytes, 537 unique actions, modal fraction 6.53%, no identical
image hashes across the two splits. The existing 80/20 seed split is preserved.
There are 54 train and 11 validation LAND examples. 26 train and nine validation
episodes have no terminal label. A 0.5 s stride can miss a terminal transition;
this must be audited with unstrided final observations rather than guessed labels.

**Correction of an intermediate claim:** there is no prompt-text drift. The
initial ad hoc comparison used Windows default text decoding rather than UTF-8,
which changed punctuation in memory and made every record compare unequal.
The strict UTF-8 audit finds zero train or validation prompt mismatches. Do not
refresh/rewrite this dataset's prompts to address a nonexistent defect.

`teacher_contract_audit.json` contains analytical counterexamples at yaw=0,
label horizon 0.25 s and the existing 1 m/s decoder. No model or flight is involved:

| Teacher command | Decoded command | Meaning |
|---|---|---|
| Hold, zero velocity | +0.5102 m/s forward for 0.1 s | Nonterminal hover is not representable by the existing zero-as-LAND contract |
| Forward 2.5 m/s | Forward 1 m/s for 0.6122 s | Label horizon and executed duration/speed differ |
| Left 2.5 m/s | (0.2777, 0.5456, 0) m/s, yaw 1.1 rad/s | 90-degree direction clips at the released 1.1-rad range |
| Yaw only 0.4 rad/s | 0.8980 rad/s for 0.1 s | Rotation timing differs |

These are representational counterexamples, not a measured error distribution
of the saved dataset and not evidence that the original AeroVLA task cannot
work. Replanning a converted C0 command at control cadence would also differ
from executing a model action for its declared duration. Validate the actual
student execution schedule before collecting replacement labels.

## Current resource revalidation

Inherited evidence ledger validation: 31 meaningful works, 27 primary sources,
seven direct solutions and seven dataset/benchmark entries; validator passes.
This is inherited research plus the bounded resource check, not 31 papers newly
re-read in this session. Exact current model/data revisions are saved in
`resource_inventory.json`. No large weights or external datasets downloaded.

| Candidate/resource | Verified now | Drone suitability and missing evidence |
|---|---|---|
| [Qwen3-VL 4B Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) | BF16 weights, Apache-2.0, official fine-tuning route | Existing planned backbone; pretrained VLM, not a trained drone controller. Requires aerial labels, correct action head/codec, latency and transfer tests |
| [AeroVLA](https://github.com/XuPeng23/AeroVLA) | OpenVLA-7B base + released aerial LoRA and training JSON; Apache-2.0 adapter | Native dual cameras, coarse prior and displacement geometry must be matched. Official README still lists hardware deployment as unfinished. Keep as native adapter reference, not real-flight proof |
| [OpenVLA-UAV / UAV-Flow](https://github.com/buaa-colalab/UAV-Flow) | Released checkpoint and real/sim resources; repo code Apache-2.0 | Worth a later native transfer check. Not a drop-in ENU velocity checkpoint. HF checkpoint/data metadata do not declare a license; repository code license is not assumed to cover all data/weights |
| [UAV-Flow data](https://huggingface.co/datasets/wangxiangyu0814/UAV-Flow) | 54 parquet shards, RGB and timestamped pose logs | Pose differences estimate achieved motion, not necessarily commanded actions. Need camera/extrinsic, local frame, angular units, time alignment and smoothing audit; do not fabricate down-camera images |
| [Exp2VLA MultiObject](https://huggingface.co/datasets/UPB-RAT-VLA/Exp2VLA-MultiObject-v1) | Current release has metadata, parquet and camera video | Prior primary-source audit identifies normalized 3-axis control, not arbitrary metric 4-axis velocity. Scaling and action omissions need explicit adapters; no bulk import |

The old survey's blanket conclusion that discrete navigation data are unusable
is too strong: they may support semantics or their native action task. They
cannot simply be concatenated as continuous velocity demonstrations. Similarly,
ground-manipulation pretraining can initialize representations but its action
head is not a drone controller. No broad model sweep is proposed.

## Hardware recommendation and approval boundary

Remote instance existence, GPU, VRAM, disks, OS, packages, account GPU quota,
credits and billing mode remain **unknown**. The user supplied the Stockholm
console URL. Browser initialization failed twice before any page was accessed:
Windows sandbox `apply deny-read ACLs` / setup-helper error. Local shell works
only with explicit tool escalation. No credentials were read or printed.

Use `python3 scripts/inventory_training_host.py --storage /actual/training/path`
on the actual host after SSH/SSM access exists. It reports GPU/driver, CPU/RAM,
block storage/free space and installed package versions, without credential,
environment or hostname enumeration. Optional `--torch-probe` checks CUDA/BF16.
The saved `local_inventory.json` is explicitly the laptop, not AWS. Its second
snapshot had about 14.8 GiB disk free and 7.26 GiB GPU occupied by existing work;
no existing process or shared model was interrupted.

Recommend **one g6.2xlarge**: L4, 24 GB VRAM, 8 vCPUs, 32 GiB host memory.
One device is a reasonable first QLoRA fit target, not a measured fit guarantee.
Eight GPUs would introduce distributed training before correctness is known.
If memory fails, inspect peak usage and reduce batch/resolution/sequence length
within the frozen contract before considering a more expensive machine.

Official public price list checked 2026-09-16, effective 2026-09-01, Linux shared
On-Demand in eu-north-1 (saved SKUs and source in `public_aws_prices.json`):

| Instance | GPU VRAM | Host RAM | Compute USD/hour |
|---|---:|---:|---:|
| g6.xlarge | 24 GB | 16 GiB | 0.85360 |
| **g6.2xlarge** | **24 GB** | **32 GiB** | **1.03688** |
| g5.2xlarge | 24 GB | 32 GiB | 1.28549 |

**D-125 correction:** the following 100 GB / 5 USD figures describe the old
tiny-pilot proposal only. They are not a full-dataset storage budget. Use the
measured storage plan below for subsequent launch decisions.

100 GB gp3 at baseline performance: 0.0836 USD/GB-month = 8.36 USD/month
while provisioned, even when the instance is stopped. A two-hour compute window
is 2.07376 USD; one day of 100 GB storage is approximately 0.279 USD using a
30-day month. Public IPv4, transfer, snapshots and tax are separate. Proposed
initial envelope: two hours maximum instance uptime and a 5 USD pilot allocation,
subject to exact account charges and storage retention approval. This is a
proposal, not authorization or an installed spending guard. Promotional credit
activities in the screenshot do not establish a usable balance.

Before launch: user approves exact instance/region/disk/AMI hourly charges,
maximum uptime, storage retention and a maximum dollar amount. Inspect quota and
capacity read-only. Use a no-extra-fee AMI; do not infer Marketplace charges are
covered. Before training: show measured memory/throughput and the bounded command,
then ask again as requested. Use a verified independent instance stop deadline;
process timeout alone does not stop EC2 billing. AWS budget alerts alone are not
a hard cap. Do not silently expand machines or runtime.

## Smallest useful experiment (proposed, not executed)

1. **CPU data/control gate.** Retain the old data for reproducibility. Record an
   exact teacher observation -> label -> decoded action -> executed trajectory
   trace on training scenes. Resolve hover, yaw clipping, cadence, terminal
   observability and source-camera timing. A native reproduction keeps native
   semantics; a broader normalized velocity/stop interface must have a new name
   and its own matching deployment path. No changes to the existing baselines.
2. **Tiny overfit.** Eight to sixteen audited training samples covering straight,
   left/right, climb/descend, nonterminal hold (if supported) and terminal actions.
   Reserve validation scenes first. Use assistant-only loss; verify nonzero,
   finite LoRA gradients and changed adapter weights; save/reload the adapter.
   Require 100% strict JSON parsing and >=95% action dimensions within one bin
   on the memorized examples, with correct terminal/hold separation. This is a
   pipeline test, not generalization. Cap at 200 optimizer steps / 20 minutes.
3. **Short pilot.** Same Qwen3-VL 4B base and rank-8 QLoRA, frozen vision/aligner,
   224-pixel input, max_length initially 512 with a no-truncation assertion.
   Start with 32 complete successful training episodes, approximately 1,000
   de-correlated transitions; fixed existing validation seed assignment.
   Cap at 64 optimizer updates, accumulation 8, or 45 minutes, whichever comes
   first. Do not quietly promote the old three-epoch full run to this pilot.
   Measure optimizer-step seconds after warmup and revise the estimate before
   training. Planning allowance: setup 30 min, overfit 20 min, pilot 45 min,
   evaluation 15 min plus stop margin within the two-hour envelope. These are
   operational caps, not measured runtime predictions.
4. **Offline gate.** Strict parse >=99.5%; terminal precision >=95%, recall >=90%
   on a separately curated terminal-balanced validation set; report denominators
   and intervals. Eleven existing validation positives are insufficient to make
   a strong reliability claim. Report action errors in physical units and
   response to image/instruction perturbation against modal/zero-action controls.
5. **Closed-loop development.** Frozen 1060-1064 schedule, same checkpoint and
   hardware, C8 base and C7 shield ablation only after codec gate. Pilot target:
   >=3/5 task successes with zero collisions and no fallback/oracle stop; full
   old gate remains 4/5 before even considering separately authorized held-out
   scoring. A one-regime pilot does not establish eight-regime capability.
6. **Debugger.** Capture every input mosaic, instruction, source timestamp,
   raw model JSON, decoded body/world action, duration, shield modification,
   control actually sent, vehicle state, stop decision and latency. Use existing
   `--debug-capture` and zero-inference `uavlab debugger`; never label analytical
   codec probes or teacher flights as model predictions. Compare unshielded
   proposals and shielded controls at the same source observation to separate
   data, model and control failures. No new trained-policy flight exists yet.

Expected pilot cost at this proposed bound: about 2.07 USD compute plus storage
and applicable extras, within a proposed 5 USD allocation if approved and the
retention/stop controls are verified. Full training cost remains unknown until
samples/second and the mixed-domain dataset are measured.

## Data required beyond this pilot

More of the same adjacent frames is not enough. The paper's first authority
screen needs semantic navigation, unknown-location search and continuous visual
control; later coverage must include state reasoning, conditional behavior,
ordered stages and recovery. One instruction with seven bearing buckets does
not test language grounding. The current bearing-dependent, reactive profile
cannot be silently advertised as an executor for all of these tasks.

Build a source manifest with episode/scene IDs, simulator or real source,
airframe, calibration/extrinsics, timestamps, camera availability, coordinate
frame/units, actual control cadence, action type, teacher identity, task category,
instruction and terminal semantics. Keep privileged labeling fields separate
from student inputs. Group splits by scene/site/episode and instruction template;
protect original external test splits and local seeds 1-40. Keep 1060-1064 out
of this pilot's collection, even though the broad legacy range includes them.

Stage external data with a small schema/calibration sample first. Do not infer
commanded velocity from achieved pose differences without explicitly labeling
that proxy and testing its error/lag. Preserve missing sensors as missing. Add
multi-task in-domain demonstrations, photorealistic sim sources and real flight
data only after each passes its own unit/frame/cadence checks. Freeze domain and
task validation sets before iterating. Use learning curves at increasing episode
counts and cross-domain evaluation to decide adequacy; no dataset-size number
alone certifies a deployable VLA. A provisional next scale is hundreds to a few
thousand diverse episodes, not a commitment to launch that training now.

Transfer validation must include a second simulator's control adapter and a
real-flight replay/shadow-control gate with the intended onboard hardware.
Neither public native benchmark scores nor this flat-shaded simulator establish
real-world readiness. Keep the same frozen trained executor across C8/C10/C12
when those architecture comparisons are eventually run.

## Implemented commands and checks

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -m uavlab.training.qwen_vla_preflight ../uav_arch_lab/data/qwen_vla_sft
python -m uavlab.training.qwen_vla_preflight ../uav_arch_lab/data/qwen_vla_sft --export data/NEW_PORTABLE_COPY --report reports/NEW_AUDIT.json
python scripts/audit_vla_teacher_contract.py --out reports/NEW_TEACHER_AUDIT.json
python scripts/inventory_training_host.py --out reports/NEW_HOST_INVENTORY.json
```

New exports use paths relative to the dataset working directory and explicitly
record that root in the manifest. Original images, labels, train/validation seeds
and historical files remain unchanged. Do not run the legacy PowerShell trainer
against this export: it expects the historical format and remains frozen. A
bounded Linux trainer/adapter-loading route is still to be validated on the GPU.
The auditor deliberately reports `training_ready=false` while semantic gates
remain unresolved; a successful audit exit is structural validation only.

Validation: 97 focused unit/contract tests pass; Ruff passes for all four new
Python files. Portable export image hashes and split identities match the source;
relocation, corruption, duplicate coverage, forbidden seeds, strict target types
and explicit prompt refresh are tested. No tiny overfit, trained-policy simulation,
AWS launch, paid call or cloud spend was performed by this task.



## D-125 correction: separate root disk from dataset working storage

The user correctly challenged 100 GB as a complete training/benchmark disk.
It was a tiny-pilot estimate and failed to budget external corpora, extracted
simulators, preprocessing/cache duplication, checkpoints and disk headroom.
No volume had been provisioned. This section supersedes the earlier disk sizing
for the broader project; it does not authorize spending or bulk downloads.

Read-only public Hugging Face file-tree inventory on 2026-09-16 (all pages
followed; individual paths/byte sizes saved in `storage_inventory.json`):

| Published repository | Download bytes, decimal GB | GiB |
|---|---:|---:|
| wangxiangyu0814/UAV-Flow | 258.015 | 240.295 |
| wangxiangyu0814/UAV-Flow-Sim | 35.926 | 33.459 |
| wangxiangyu0814/TravelUAV | 482.696 | 449.545 |
| wangxiangyu0814/TravelUAV_env | 83.732 | 77.982 |
| UPB-RAT-VLA/Exp2VLA-MultiObject-v1 | 1.052 | 0.980 |

Total about 861.4 GB / 802.3 GiB in published files. This sums repository files,
not a deduplicated required dataset subset. Archive expansion, selected maps,
caches, intermediate frames and checkpoints are additional, as applicable;
unpacked size is not yet measured. These are storage candidates, not approval
to combine their data or assume they share action formats/licenses.

Revised staging proposal:

- Root: 100 GiB gp3, or the selected AMI's higher minimum if required.
- Initial working data volume: 512 GiB gp3 for selected pilot shards/maps.
  This is explicitly insufficient for all of the listed repositories at once.
- Provisional full-data target: separate 2,048 GiB (2 TiB) gp3. Confirm the
  selected archive expansion/caches before committing to this as sufficient.
  Compute required space as root software separately, then source bytes kept
  locally + extracted files + materialized training/cache bytes + retained
  checkpoints + at least 20% free working headroom; do not double-count when
  source and extracted representations are the same files.
- Increase the EBS volume before larger downloads, then extend its filesystem;
  AWS supports size increases, not in-place shrinking. Therefore staged sizing
  follows the user's request to proceed gradually.
- g6.2xlarge also has a nominal 450 GB local NVMe instance store. Use it only
  for reproducible temporary caches: it is erased on stop/termination and is
  not the persistent dataset/checkpoint store. Its capacity was omitted from
  the earlier proposal; it does not remove the persistent-storage requirement.

At the already verified Stockholm baseline gp3 rate (0.0836 USD/GiB-month):

| Root + data | Storage/month | Approx. storage/day (30-day month) |
|---|---:|---:|
| 100 + 512 GiB | 51.16 USD | 1.71 USD |
| 100 + 2,048 GiB | 179.57 USD | 5.99 USD |

Storage is charged while provisioned, including stopped-instance periods.
Two hours of g6.2xlarge compute plus a full day of the larger storage is about
8.06 USD before other charges, so the earlier proposed 5 USD allocation cannot
be carried over unchanged. Agree retention and total cap before provisioning.
No EBS/S3 resources or billing settings changed in this correction.

AMI screenshot: x86_64, Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.13
(Ubuntu 26.04), quick-start catalog, G6 listed as supported. AWS's current
release documentation confirms this image family exists. It can serve as the
GPU host; do not claim ms-swift/PEFT/bitsandbytes or older native benchmark
stacks are validated against its preinstalled Python/PyTorch. Use a separately
pinned environment/container and pass the import/CUDA/one-batch gate first.
Exact regional AMI owner/fees remain a prelaunch check; family documentation
alone is not an account-level AMI attestation.

Sources:
- https://huggingface.co/datasets/wangxiangyu0814/UAV-Flow/tree/main
- https://huggingface.co/datasets/wangxiangyu0814/UAV-Flow-Sim/tree/main
- https://huggingface.co/datasets/wangxiangyu0814/TravelUAV/tree/main
- https://huggingface.co/datasets/wangxiangyu0814/TravelUAV_env/tree/main
- https://huggingface.co/datasets/UPB-RAT-VLA/Exp2VLA-MultiObject-v1/tree/main
- https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-x86-gpu-pytorch-2.13-ubuntu-26-04.html
- https://docs.aws.amazon.com/ebs/latest/userguide/ebs-modify-volume.html
- https://aws.amazon.com/ec2/instance-types/g6/
- https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-store-lifetime.html
