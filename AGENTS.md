# AGENTS.md — start here

Entry point for an agent picking up this repository. It says where the work
stands, what to do next, and which rules must not be broken. It deliberately
does not restate the evidence: every claim below names the decision that holds
it, in [`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md).

Read [`docs/README.md`](docs/README.md) first for what belongs in which file.
A new decision goes in `RESEARCH_LOG.md` with a new `D-nn`, rationale and
evidence. Corrections never delete the old entry; they mark it superseded.

## What this testbed is

A modular testbed for searching single-UAV foundation-model autonomy
architectures. Architectures are composed from configuration (`configs/`), run
against a deterministic simulator, and charged model latency on a simulated
clock. Seven families are the base; everything else is an ablation.

## D159 CURRENT STATE - read this first (2026-09-23)

Supersedes the D157/D158 sections below wherever they conflict. Evidence is in
CHANGES.md (D158, D159) and docs/VLA_DRONE_TRAINING.md sections 13-15.

### Goal (user, unchanged)

A VLA that runs next to the testbed's VLM on one 8 GB GPU, and the user having
trained a VLA themselves. The user explicitly does NOT want to reproduce the
official recipe on all 30k flights with a 4B model ("we will get worse results
because of model size"); the aim is better results on less data. Beating WorldVLN
(79.1% SR) was agreed to be unrealistic here; the honest angle is efficiency plus
an honest closed-loop number.

### The one open problem: our adapters barely use the camera

- D155 format (6-DoF start-frame 8-step chunks, no state), Qwen3-VL-4B bf16,
  1 shard, best checkpoint: held-out endpoint error 6.474 m, IDENTICAL on real,
  gray and swapped frames; text-only bar 4.496 m. Camera-blind and worse than text.
- The released OpenVLA-UAV on the same frames CHANGES its action in 16/20 when the
  photo is mirrored (6/20 flip the sideways sign) - so the target is reachable.
- The base VLM is not at fault: Qwen3-VL scores 24/24 on a pasted red rectangle
  (left/right) at 512 px. Resolution is not the bottleneck either (flip rate 2/12
  at 256, 512 and 896 px). 83% of flights name a visual target, so filtering
  instructions by "has a target" is pointless.
- Official-format K=1, 1 shard, 1 epoch: mirroring changes 10/60 (16.7%) at the
  end of training and 0/60 before it. Weak but no longer zero, which points at
  data scale and training length rather than a dead end.

### Data and code (this worktree)

- scripts/prepare_uav_flow_official.py - the official OpenVLA-UAV format: 4-D
  (dx,dy,dz,dyaw) in the drone's local frame from raw_logs [0,1,2,4], yaw deg to
  rad, zero last action, proprio = preprocessed [0,1,2,4] written into the prompt,
  every frame, first/last repeated 5x. Verified 0 mismatches against the official
  loop on 5,000 flights; re-integrated xy matches the dataset to 5 mm. Streams
  shard by shard (pass 1 logs for the site split, pass 2 images), so 10 shards fit
  in 30 GB RAM. --clip-percentile sets the action range (1.0 = official q01/q99,
  0.1 = wider), --shard takes several parquet files, --out sets the manifest dir.
- scripts/train_uav_flow_vla.py - --format official, --chunk K, --instruction
  {instruction,instruction_unified,both}, --mirror (left-right mirrored copy:
  photo flipped, dy and dyaw negated, side words swapped; verified that the
  mirrored chunk integrates to the mirrored path), --precision bf16,
  --batch-size/--accum/--workers, --schedule cosine, --save-every/--resume,
  --epochs, --wandb-project (entity defaults to `asael`), torchrun DDP (untested).
- scripts/score_uav_flow_official.py - open-loop rollout of a K-chunk adapter:
  floor/real/gray/swap, endpoint error, first-step MAE, seconds and tokens per
  call, text baselines recomputed on the same endpoints. KNOWN DEFECT: the floor
  condition fails to parse flights whose length is not a multiple of K.
- scripts/probe_mirror_vla.py - the camera test used above (real vs mirrored).
- scripts/probe_image_resolution.py - the VLM perception probe (red rectangle,
  resolution sweep).

### Data facts worth knowing

- The official q01/q99 action cap clips 24.5% of steps; with perfect predictions
  it still costs 4 m or more of endpoint error on 10% of flights (yaw cap
  0.105 rad/step = 30 deg/s, forward 0.46 m/step, while the largest yaw step in
  the data is 3.1 rad). The 10-shard store therefore uses percentiles 0.1/99.9.
- raw_logs altitude and preprocessed_logs altitude disagree (median 0.19 m, max
  6.8 m). The official code mixes them (action dz from raw, state z from
  preprocessed) and we inherit that. Caveat any height result.
- Every flight carries `instruction` (free wording, what the official code trains
  on) and `instruction_unified` (fixed template); 478/500 differ in shard 0.

### RUNNING NOW (2026-09-23)

- Instance i-0751e8ef73191703e, g5.2xlarge (A10G 23 GB), us-east-1d, IP
  98.87.4.20, user ubuntu, key C:\Users\Asael\PycharmProjects\keys\asael_aws.pem,
  $1.21/h, auto-stop 2026-09-23 18:44Z. The AWS connector must be reconnected by
  the user from connector settings whenever a call says it was invalidated.
- Remote layout: code ~/vla, 10 raw shards ~/data/uav_flow_raw (45 GB), prepared
  store ~/data/uav_flow_official_10shard (5,000 flights: 1,987 train / 791 val /
  2,222 dropped by the instruction sweep), base model ~/qwen3vl4b, interpreter
  /opt/pytorch/bin/python. Env: QWEN_MODEL, UAV_FLOW_OFFICIAL_STORE,
  PYTHONPATH=~/vla/src:~/vla/scripts. NOTE: train_uav_flow_vla.py ON THE INSTANCE
  was sed-edited so OFFICIAL_REPORT points at reports/uav_flow_official_10shard;
  redo that edit after any re-upload.
- Run: ~/runs/official_k8_10shard, log ~/k8.log, wandb
  asael/vla training/official_k8_10shard. Official format, K=8, bf16,
  --instruction both --mirror, batch 8 x accum 4 = 32, lr 5e-4 cosine, 2,500
  updates (about 5 h, about $6), checkpoint and adapter_s<step> every 250.
  Held-out loss (128 examples): 11.02 -> 2.94 (step 250) -> 2.57 (step 2250),
  still falling at the end - no overfitting, unlike the 1-shard run.

### RESULT of the 10-shard run (D160, 2026-09-23)

150 unseen-site flights, open loop: real 3.067 m, gray 3.115 m, swap 3.121 m,
text-only 4.533 m, no-text 4.208 m, floor 0.072 m. Beats text baselines by
~1.1 m, but the camera adds only ~0.05 m (not significant); mirror changes 23%.
The gain is from state + instruction. Instance STOPPED after scoring.
Mirror trend by checkpoint (D161): 0/11/19/14/12/26% at s250..s2500 -
rising but noisy, no saturation. Instance stopped again after the trend probe. Scoring is
now batched (--batch-size 8, 0.35 s/call) and frame prep is threaded.

### D162 closed-loop simulator (2026-09-24) - see CHANGES.md D162

UAV-Flow-Eval runs locally (4060) with the UnrealZoo build on D:. OpenVLA-UAV
full 273-task run in progress; ours blocked until the adapter is copied off the
stopped instance (AWS connector must be reconnected). Server
scripts/uav_flow_eval_server.py, scorer scripts/score_uav_flow_sim.py.

### D165 IN PROGRESS (2026-09-25): real + simulator training - CHANGES.md D165

Linux g5 runs scripts/aws/sim_pipeline_d165.sh via SSM (SSH blocked: user IP
changed), uploads s3://vla-eval-artifacts-512068640697/d165/realsim_adapter.tgz
and stops itself (hard stop 04:36 UTC). Then evaluate it on the Windows box.

### D164 RESULT (2026-09-25): ours nDTW 0.129 vs OpenVLA-UAV 0.395 (100 tasks)

Same Windows closed-loop tasks; theirs better on 77/100; ours stops early and is
near zero on Surround, Land and Ascend/Descend. Details and caveats in
CHANGES.md D164. Both instances stopped.

### D163 WINDOWS CLOSED-LOOP EVAL (2026-09-24) - read CHANGES.md D163

OpenVLA-UAV on the official Windows build, 100 stratified tasks: mean nDTW
0.395 (paper's SR 65.6% is a different, human-judged metric). Our adapter's
rerun was launched but the user STOPPED the instance before it finished (0
tasks done). Restart i-03a3c8632314bf5fc and rerun C:
unsinish.ps1 via SSM. To finish: presign-download s3://vla-eval-artifacts-512068640697/
results/qwen.zip (backslash paths - unzip with chr(92)->'/'), score with
scripts/score_uav_flow_sim.py, compare per class with
D:/drone_vla_pilot/runs/sim_eval_win/openvla/score.json. Confirm the instance
is stopped. The Linux g5 i-0751e8ef73191703e is stopped (GPU quota is 8 vCPU:
only one G machine may run at a time).

### Next steps, in order

1. (DONE, see D160) When the run ends: re-score the best checkpoint on a MUCH larger held-out
   sample (the user rightly called 128 examples too small) and run
   probe_mirror_vla.py on the checkpoints. Compare the mirror change rate with
   OpenVLA-UAV's 16/20 and the endpoint error with the text-only baseline.
2. Then stop the instance. "Stop the run" means the training process only; stop
   the machine only when the user says machine or instance.
3. Get UAV-Flow-Eval (UnrealZoo, Windows) running for a real closed-loop number.
   It is also the prerequisite for RL.
4. Only then consider RL (SimpleVLA-RL: 17.3% -> 91.7% from one demonstration per
   task; WorldVLN: +10 points after SFT saturates) and, last and only if needed,
   a bigger run on a p4d (P quota request 8e333ae19c934fcaafcc4b2f6f98d161vL9uhsKE,
   case 179008835200067, still CASE_OPENED).

### Experiment plan (docs/VLA_DRONE_TRAINING.md section 15)

E0 baseline, E1 training length, E2 action cap, E3 horizon, E4 free data (both
wordings + mirror), E5 history, E6 sim data, E7 FAST tokens, E8 offline RL,
E9 simulator RL, E10 combine the winners. The current run is E0+E1+E2+E3(K=8)+E4.
Only RL and data scale have published evidence behind them; the rest are guesses,
and the user's constraint is implementation risk, not compute.

### Standing rules

- Report the image control (gray/swap/mirror) and the text-only baseline beside
  every model number. A model number alone is not a result.
- The user cannot read long replies: one idea, at most 8 lines, one question.
- Ask before any AWS launch or spend.
- Dataset licence is settled (research use). SmolVLM training is dropped.

## D157 CURRENT STATE - read this first (2026-09-21)

Supersedes the D154 plan below. Detail and evidence for every point is in
CHANGES.md (D152-D157) and docs/VLA_DRONE_TRAINING.md.

### What the user actually needs (corrected 2026-09-21)

The research questions are the ones in this repo's papers (the modular
architecture testbed), NOT "do VLAs use their camera" - an earlier session
wrongly reframed the research around that. The practical requirement is:

- a VLA that runs NEXT TO the testbed's VLM on one 8 GB GPU (RTX 4060 Laptop),
  driving AirSim or the local renderer, possibly with shared KV cache;
- the user also wants to train a VLA themselves.

### Runtime facts

- Testbed VLM = Qwen3-VL-4B via Ollama `qwen3-vl:4b`: GGUF Q4_K_M, 8,192 ctx,
  about 4.2 GB. Not AWQ.
- Ollama 0.34.2 runs qwen3vl on its new engine and NO LONGER SUPPORTS LoRA
  adapters (ollama server/create.go: "LoRA adapters are no longer supported";
  server/model.go: new adapters cannot be created). Do not plan around Ollama
  adapters.
- Ollama's qwen3-vl:4b blob is one combined GGUF (396 text + 411 vision tensors).
  llama.cpp needs text + a separate mmproj, so it uses the official files instead.
- Other experiments share this GPU (seen: scripts/valley_operator_experiment.py).
  Check nvidia-smi before loading anything and never kill a process you did not
  start. A viewer http.server on 127.0.0.1:8771 was left running by that session.

### Decision: the VLA is a LoRA on the VLM's own base, served by llama.cpp

- One Qwen3-VL-4B base in llama.cpp `llama-server`; the action LoRA is loaded with
  --lora-init-without-apply and switched per request via the `lora` field
  ([{id:0, scale:1}] for VLA, scale 0 for VLM).
- Weights are shared. The KV cache is per request and cannot be reused across a
  VLM call and a VLA call (the adapter changes the projections) - that is fine,
  weights are where the memory is. Always send cache_prompt=false when switching
  scales; a prompt cache built under one scale is invalid under the other.
- Memory, computed from the real dims (36 layers, 8 KV heads, head dim 128 =
  144 KB/token fp16): shared = 4.2 GB + 0.13 GB adapter + 0.28 GB VLA KV at 2k
  = about 4.6 GB. Two separate model copies = about 8.4 GB and do not fit.
- SmolVLM is DROPPED (user decision): Exp2VLA trained SmolVLA properly and got
  46.6% single-object against pi0.5's 84.1%.
- No released VLA can share the VLM's base: OpenVLA-UAV is Llama-2-7B (5.15 GiB
  alone at 4-bit), pi0.5 is PaliGemma.

### D157 chain test - reports/vla_llamacpp_chain_20260921/

Tiny adapter: Qwen3-VL-4B NF4 + LoRA rank 32 on language_model.layers, 60 updates,
D:/drone_vla_pilot/runs/qwen_chain_test/adapter_s60.

1. PEFT LoRA -> GGUF WORKS. llama.cpp source at tag b11081 cloned to
   D:/drone_vla_pilot/llamacpp/src; convert_lora_to_gguf.py produced
   models/uav_flow_vla_lora_s60.gguf, 504 tensors (36 x 7 x 2), 132 MB.
2. llama-server LOADS base + vision projector + adapter. Binaries
   D:/drone_vla_pilot/llamacpp/bin (b11081, CUDA 12.4 Windows); models
   Qwen3VL-4B-Instruct-Q4_K_M.gguf + mmproj-Qwen3VL-4B-Instruct-F16.gguf from the
   official Qwen/Qwen3-VL-4B-Instruct-GGUF repo. 5.5 GB alongside another job.
3. Per-request toggle WORKS: scale 1 -> 100% action tokens, 20/20 complete
   8-step chunks; scale 0 -> ordinary English VLM answers, 0% action tokens.
4. Numerical fidelity NOT YET ESTABLISHED. Same adapter, same 20 frames,
   PyTorch on NF4 base versus llama.cpp on Q4_K_M base: action-token agreement
   median 50% (min 21%); 8-step chunk displacement gap median 0.116 m (max
   0.278 m) against a between-frame spread of 0.037 m, ratio 3.1. Caveat: a
   60-update adapter is near-collapsed, so the spread is tiny and the ratio harsh.
   Unresolved whether the gap is quantisation (NF4 vs Q4_K_M) or image
   preprocessing (HF processor vs llama.cpp mtmd).
   Q8_0 follow-up (base built locally from the exact HF training weights with
   convert_hf_to_gguf.py --outtype q8_0, models/Qwen3VL-4B-Instruct-Q8_0-local.gguf,
   4.28 GB): PyTorch-NF4 vs llama.cpp Q8_0 = 65% token agreement, 0.071 m gap;
   Q8_0 vs Q4_K_M = 76%, 0.049 m. Quantisation explains ~40% of the gap. The
   residual is ambiguous because the PyTorch reference is itself 4-bit NF4, not
   the true weights - Q8_0 is the closest to bf16 we have. Clean resolution needs
   a bf16 reference, i.e. train (and reference) on the full-precision base, which
   is ~9 GB and cloud-only. Q8_0 serving took ~6 GB, versus ~4.6 GB for Q4_K_M.
5. Running the VLM from the official Qwen GGUF means a different file from the
   Ollama blob the testbed's results were measured on. Confirm VLM answers match
   before trusting earlier architecture results on the new file.

### Training lane

Two paradigms exist. OpenVLA-UAV uses discrete action tokens (256 bins on the
vocabulary tail, next-token cross-entropy) - what this repo now implements.
pi0.5 and SmolVLA (Exp2VLA) use a flow-matching action expert (config fields
time_sampling_beta_*, a separate gemma_300m expert). Hyperparameters do not
transfer between them. For the deployment requirement above, discrete tokens
are strongly favoured: action tokens are just vocabulary, so they ride through
llama.cpp as a LoRA. A flow-matching expert is a separate network llama.cpp does
not run, which would break weight sharing. Lane choice is still the user's call.

Our runs so far are badly undertrained: about 6,400 examples (0.33 epochs)
against Exp2VLA's about 3.84M. The user wants real-scale training on AWS; a
single L4 (g6.2xlarge, $0.9776/h as quoted 2026-09-19 - reconfirm) was
proposed, NOT an 8-GPU node, because the trainer is single-process. Nothing has
been launched; AWS CLI is not installed and no credentials exist.

### AWS state (2026-09-22)

- AWS MCP connector is live on this account (512068640697), signed in as ROOT.
  Every account-level tool is set to "Needs approval" by the user; keep it that
  way and ask before any launch or spend.
- us-east-1 GPU quota was 0 vCPU for both on-demand and spot G/VT instances.
  Increase to 8 vCPU (quota L-DB2E81BA) requested 2026-09-22T09:21Z, request id
  8965ad1917584b8cb383594823b1212fBJ2iREdo - APPROVED, limit now 8 vCPU
  (CASE_CLOSED, confirmed via API 2026-09-22). No instances exist in us-east-1.
- Live on-demand Linux prices, us-east-1, 2026-09-22: g6.xlarge $0.8048/h
  (L4, 16 GiB RAM), g6.2xlarge $0.9776/h (L4, 32 GiB RAM, the recommended box),
  g5.2xlarge $1.212/h (A10G), g6e.xlarge $1.861/h (L40S 45 GiB).
- Intended first cloud run: full-precision Qwen3-VL-4B LoRA on the action-token
  data, so the adapter trains against the true weights (see D157 fidelity result).
- 2026-09-22 14:00Z: g6.2xlarge had NO capacity in any us-east-1 zone
  (InsufficientInstanceCapacity, not quota). User approved g5.2xlarge instead.
  RUNNING: i-0751e8ef73191703e, g5.2xlarge (A10G 23 GB), us-east-1d,
  IP 34.229.106.76 (changes on stop/start), user `ubuntu`, key
  C:\Users\Asael\PycharmProjects\keys\asael_aws.pem, AMI ami-0bf9017599376f62e
  (DLAMI PyTorch 2.13, Ubuntu 26.04, Python 3.14), 200 GB gp3 root,
  security group sg-00bde935030fcd6a2 (SSH from 147.235.193.80/32 only),
  shutdown behaviour = stop. Auto-stop scheduled 16:57Z via `shutdown -h`.
  Instance-store NVMe is wiped on stop: keep results on the root volume.
  Purpose: ~2 h bf16 speed measurement. STOP it when done and confirm.
- Remote layout: code ~/vla (scripts, src), data ~/data/uav_flow_chunks_20260921,
  base ~/qwen3vl4b (HF download), python /opt/pytorch/bin/python (torch 2.13 cu130,
  transformers 5.17, peft 0.21). Env: QWEN_MODEL, UAV_FLOW_STORE,
  PYTHONPATH=~/vla/src:~/vla/scripts. transformer_engine was UNINSTALLED from the
  venv (broken cublasLt symbol, broke `import peft`). transformers 5 returns
  mm_token_type_ids; encode() now extends it for the answer tokens.
- bf16 smoke test (12 updates, batch 1 x accum 8, all-linear r32): works, loss
  10.7 -> 6.8, peak 9.9 GiB, 4.4 s/update = 0.55 s/example. 10 epochs (195k
  examples) at that rate is about 30 h (~$36). The GPU is under-used at batch 1;
  real batching is the next speed step.
- 2026-09-22 ~14:35Z: instance STOPPED by user request (compute billing off;
  200 GB disk ~$16/month keeps code, data and model). Public IP will change on
  next start. The shutdown timer is gone after a stop; set it again on start.
- Trainer upgraded (local, 2026-09-22; NOT yet on the instance - re-upload
  scripts/train_uav_flow_vla.py): --batch-size (right-padded collate; padded
  batch loss 11.5813 vs single-example mean 11.5773), --workers (DataLoader),
  --schedule cosine --warmup, --save-every/--resume (OUT/checkpoint; resumed
  step reproduced loss 9.5928 exactly), --epochs, --wandb-project (rank 0; the
  USER must put WANDB_API_KEY on the machine - never handle it), and torchrun
  multi-GPU DDP (ranks stride one global example stream; no_sync on accum
  micro-steps; held-out split across ranks). DDP is untested until a multi-GPU box.
- User wants 8 GPUs (~1 h run) + wandb. Quotas: G/VT on-demand 8 vCPU, P = 0.
  8-GPU prices us-east-1: g6.48xlarge $13.35/h (8xL4), g5.48xlarge $16.29/h
  (8xA10G), p4d.24xlarge $21.96/h (8xA100 40GB, needs P quota 96),
  g6e.48xlarge $30.13/h. G boxes need G quota 192 vCPU.
- User chose p4d only. P quota (L-417A185B) increase 0 -> 96 requested
  2026-09-22, request id 8e333ae19c934fcaafcc4b2f6f98d161vL9uhsKE, PENDING.
  No G-192 request was made (user declined). A p4d is a new instance: data and
  model must be uploaded/downloaded again (or copied from the stopped g5 disk).
- 2026-09-22 ~15:00Z g5 speed sweep (bf16, all-linear r32, 6 workers), s/example:
  batch1 0.55, batch4 0.199, batch8 0.188 (12.1 GiB), batch16 0.180 (15.0 GiB).
  10 epochs on one A10G ~10 h (~$12); p4d estimate <1 h.
- wandb: user logged in on the instance (~/.netrc). Team entity is `asael`
  (NOT asaelbarilan-wonderful-ai / -org: 404 / "may not log to organization"),
  project "vla training". Trainer --wandb-entity defaults to asael. Demo run
  wandb_demo_b8 (200 updates, batch 8, cosine; train 10.7->4.1, held-out
  11.18->5.08) synced to asael/vla training.
- Mistake log: I stopped the instance when the user said "stop the run" (the run
  had already finished). User wanted the machine kept on. Only stop the
  instance when the user explicitly says the machine/instance.
- 2026-09-22 15:55Z LONG RUN STARTED (user approved): instance IP 32.199.249.136,
  ~/runs/shard1_bf16_10ep, log ~/shard1.log, wandb asael/vla training/
  shard1_bf16_10ep. bf16, all-linear r32, batch 8 x accum 2 (=16, official
  recipe global batch), lr 5e-4 cosine 3% warmup, 10 epochs (~12.2k updates,
  ~3 s/update, ~10 h), held-out every 250, checkpoint + adapter_s<step> every
  250. Auto-stop 2026-09-23 03:55Z; max-wall 44000 s. If stopped early, restart
  instance and rerun the same command with --resume. P quota request is
  CASE_OPENED (case 179008835200067). After the run: pick best held-out
  adapter, rollout-score vs baselines (no-text 6.868 m, TF-IDF 4.496 m), gray +
  image-swap controls, then STOP instance and ask about deleting it.
- 2026-09-22 ~17:10Z: training STOPPED at update ~1500 (user approved) because
  held-out loss rose after update 1000: 250 5.165, 500 4.848, 750 4.769,
  1000 4.689 (best), 1250 4.892, 1500 4.955 -> overfits after ~1.3 epochs of one
  shard (308 flights). Instance still RUNNING. Scoring adapter_s1000 with
  score_uav_flow_vla.py (now --model qwen --precision bf16, adds image-swap
  condition): val 62 episodes + train 20; out ~/runs/shard1_bf16_10ep/scored,
  log ~/score.log.
- OFFICIAL RECIPES (verified 2026-09-22 from code + papers):
  UAV-Flow paper (2505.15725) trains on the FULL REAL set, 30,692 flights (Sim
  10,109 is for evaluation). OpenVLA-UAV code: finetune_uav.sh batch_size 4 x 8
  GPUs = 32, lr 5e-4 constant (no scheduler), LoRA r32, max_steps default
  200,000 (~3 epochs of ~2M frames), save 20k; uav_dataset.py: every frame,
  first/last frames oversampled 5x, ONE-STEP action (dx,dy,dz,dyaw) in the
  drone's LOCAL frame (rotated by current yaw), prompt "Current State: {proprio},
  What action should the uav take to {instruction}?", q01/q99 -> [-1,1].
  Pi-0-UAV: chunk 10, batch 16, 12 epochs, lr 5e-5. WorldVLN (2605.15964):
  InfinityStar-8B, (dx,dy,dz,dpsi) chunks K=16, SFT lr 1e-5 + GRPO; 79.12/78.02 SR
  vs OpenVLA-UAV 65.61/65.33. ImagineUAV (2606.01205): Wan2.1 1.3B, 2 epochs on
  30k real + 10k sim, 70.9% SR. Exp2VLA did NOT use UAV-Flow (own Isaac data).
  Our shard run deviates: 1% of data, 6-DoF world-frame 8-step chunks, no state.
- USER DIRECTION 2026-09-22: p4d/all-shards run is the LAST step, only if needed.
  First: decide the prediction horizon (steps ahead) and apply lessons from all
  UAV-Flow papers (docs/VLA_DRONE_TRAINING.md section 13), running as many
  single-GPU tests as possible. Stop the g5 after scoring finishes (user: yes).
- D158 (local): scripts/prepare_uav_flow_official.py ports the official
  uav_dataset.py (4-D local-frame actions from raw_logs [0,1,2,4], yaw deg->rad,
  zero last action, proprio = preprocessed [0,1,2,4], every frame, first/last
  x5 extra). Output D:/drone_vla_pilot/data/uav_flow_official_20260922/
  episodes.jsonl (+frames incl. last frame), manifest
  reports/uav_flow_official_20260922/manifest.json. Same D155 unseen split
  (308/62/130). 0/500 mismatches vs a verbatim restatement of the official loop.
  Independent check: local actions re-integrated match preprocessed xy to 5 mm
  median (transform correct) but Z differs: raw z vs preprocessed z median 0.19 m,
  max 6.8 m (different altitude sources in the dataset; official code inherits it).
  Official trains on `instruction` (free wording); D155 used instruction_unified;
  478/500 differ. Next: trainer support for 4-D + state prompt + K-step chunks
  from per-frame actions (horizon test K=1/8/16).

### Assets on disk

- OpenVLA-UAV: D:/drone_vla_pilot/models/openvla-uav (runs at 4-bit, 5.15 GiB;
  action dim 4 = x, y, z, yaw rad; unnorm_key "sim"; prompt includes proprio).
- Exp2VLA pi0.5: D:/drone_vla_pilot/models/exp2vla-pi05 (LeRobot pi05 policy,
  needs the lerobot package; not yet run; paper reports 12.9 GB VRAM).
- UAV-Flow chunk data + unseen split: D:/drone_vla_pilot/data/uav_flow_chunks_20260921.
- Trainer: scripts/train_uav_flow_vla.py --model qwen (4-bit, grad checkpointing,
  vision frozen = the Exp2VLA expert-only regime).

### Settled - do not reopen

- Dataset license: the user decided it is fine for research use. Do not raise it.
- SmolVLM training: dropped.

### Standing rules

- Beside every model number report the image-swap control and the text-only
  baseline. A model number alone is not a result.
- The user cannot read long replies. One idea per reply, at most 8 lines, one
  question at the end.

## D154 plan (SUPERSEDED by D157 above): closed-loop first, then three models on AWS, then RL

Read docs/VLA_DRONE_TRAINING.md for the whole picture, then this. Supersedes the
earlier D154 note. User direction of 2026-09-21: get the official closed-loop
evaluation running on Windows, train smol256/smol500/qwen, move training to AWS
rather than the local 4060, and keep RL as a later improvement - but verify the
whole pipeline works before any cloud spend.

Standing rule, unchanged and applying to every phase below:
report the blinded (flat gray image) control AND the text-only baseline beside any
model number. A model number alone is not a result. D152 exists because four
models were ranked on a metric a no-vision oracle beat.

### Phase A - make it real, locally, before spending anything

A1. Stand up UAV-Flow-Eval on Windows. github.com/buaa-colalab/UAV-Flow is
    Apache-2.0 and ships UnrealZoo Gym plus the packaged Collection_WinNoEditor
    build and the DowntownWest campus map. This is the opposite of the D151
    blocker: that failed because OpenFly needed a Linux graphics stack. Gate:
    replay a recorded expert trajectory and have the environment reproduce it.
    Until that passes, no flight number from any model is meaningful.
A2. Stand up their inference server contract (vla-scripts/openvla_act.py) so our
    own models can be driven by batch_run_act_all.py through the same port. We
    substitute the model, never the evaluator.
A3. Train ONE small model end to end locally (next-step 6-DoF, data already built
    at reports/uav_flow_steps_20260921, 28,304 train / 5,714 val steps) and run it
    through A1+A2. Purpose is to prove the pipeline, not to get a good number.
A4. Only when A1-A3 pass is the pipeline considered verified.

### Phase B - three models, trained on AWS

B1. Do not launch anything until Phase A passes and the user approves a concrete
    machine and cost. No AWS resource has ever been started by this project.
B2. Train smol256, smol500 and qwen on the same frozen split, one change at a
    time, each scored with the blind control and the text-only baseline (2.264m)
    and then through closed-loop evaluation from A1.
B3. Sizing note: the official recipe is openvla-7b, LoRA rank32, batch2,
    lr 5e-4, 8 GPUs. Our models are far smaller, so a single modern GPU is the
    starting point, not an 8-way node. Price the instance against the real
    measured step time from A3 before proposing it.
B4. Data scaling belongs here too - further shards at 4.7GB and about 500
    episodes each. Data before updates, data before model size.
B5. The published 79.12/70.9/59.0 numbers are on UAV-Flow-Sim (33.5GB), not the
    real set. Matching them needs that dataset and their harness, and is a
    separate decision.

### Phase C - RL, only after supervised training is honest

C1. Prerequisite: a working closed-loop environment from A1 and a supervised
    checkpoint that beats the text-only baseline. RL on top of a policy that
    loses to an instruction lookup would only optimise the wrong thing.
C2. The reward must not be the metric we already know is gameable. Use the
    closed-loop task outcome, and keep the blind control as a diagnostic on the
    RL policy too.
C3. Scope it as a named ablation against the supervised checkpoint, not as a
    replacement for it.

### Carried over, still open

- UAV-Flow and UAV-Flow-Sim declare NO dataset license. The code repo is
  Apache-2.0; that does not cover data. Blocks publication.
- A rollout over recorded frames is not closed-loop flight. Do not compare to
  published success rates until A1 is running.
- OpenFly decoder calibration unresolved: 24 of 72 outputs fail to parse.
- The paper's OpenFly section must not present 20/20/21/24 as a ranking.
- Prior art on small models here is discouraging: Exp2VLA trained SmolVLA and
  reported 46.6% single-object / 15.0% multicolor against pi0.5's 84.1/65.0, and
  released only the pi0.5 weights. Expect the small-model study to be a study,
  not a win.

## D152 blind control: only the released model uses the camera

Read reports/vla_blind_control_20260920/REPORT.md and summary.json. All four
models answered the aligned72 panel twice: real frames, then every frame replaced
by flat gray, same prompts/checkpoints/greedy decoding. Harness verified first:
smol256 and openfly_vla reproduced the stored D147 predictions exactly (72/72
identical action ids; openfly_vla also 72/72 identical action tokens), and all216
frames were SHA256-checked against the frozen panel.

Real versus gray /72: openfly_vla20->10 (changed35, McNemar p=0.0213),
smol256 20->15 (changed64, p=0.4869), smol500 21->14 (changed64, p=0.2478),
qwen 24->20 (changed55, p=0.5966). Always-forward reference is12/72.

openfly_vla is the only model whose agreement depends on the image: right because
of vision on13 cases against3 the other way. Our three adapters move55-64 of72
answers when blinded but gain no separable accuracy from vision. The D147 ranking
is therefore inverted with respect to grounding: qwen leads while contributing
nothing measurable from vision, and openfly_vla trails while being charged24
unparsed outputs as wrong (20/48 with vision versus10/38 blind).

D147's earlier gray control used24 cases from the openfly: panel, sharing only13
(route,frame) pairs with the aligned72; do not cite it as a same-panel control.
Do not use next-direction agreement to rank these models: all CIs overlap, it is
not flight success, and it rewards a text prior as readily as grounding. A blind
control proves a score is not image-driven; it does not make an image-driven score
good. Decoder calibration is still unresolved (24/72 openfly_vla outputs fail to
parse under vlnv11). Next: fix that parse failure before any further comparison,
and decide grounding before more training or renderer work.

Viewer: localhost8771/blind_control.html - all21 routes, every decision, the three
causal frames each model received, four models under both conditions.
evaluate_joint_repair_controls.py gained optional --panel/--out-dir/--tag; default
behaviour unchanged. No training, no weight/adapter/split/seed changes, no AWS.

## D151 native renderer gate failed locally; HF access is resolved

Read reports/vla_openfly_renderer_20260919/REPORT.md and status.json. Official
scene is verified/extracted; six bounded WSL renderer probes produced no usable
images. Official SDK/arming/clock controls still report spawn pose and image
request timeout. Vulkan is CPU llvmpipe, but the root cause is unresolved; do not
call this a model failure. All owned renderers ended; original settings restored.
No new inference/training or AWS resources. Viewer banner states actual blocker.
Next: same scene/pose on native Linux NVIDIA graphics; machine/cost approval
pending. Proposed one g6.2xlarge Virginia, 2 hours, expected $2-3, proposed $5 cap;
verify account/AMI/connection and cleanup controls before any launch. This is a
single-scene diagnostic, not full training. Baselines/splits/weights unchanged.

## D150 execution/source audit complete; renderer outcome in D151

Read reports/vla_openfly_execution_20260919/REPORT.md. Three frozen dev routes
reconstruct exactly with corrected macro starts; old annotation frames drift up
to6source units. Native pose adapter matches upstream40cases and rejects invalid
outputs. Released evaluator teleports, ignores collision and counts endpoint-only
success even after timeout/error; keep strict diagnostic metrics separate.
All20RLDS subset metadata/statistics audited:87,157packed TRAIN episodes/460.44GB.
vlnv8 has vertical max2 but q99zero: UP/DOWN cannot round-trip. Old raw routes'
exact subset mapping remains unresolved; do not infer it from environment alone.
Added original vlnv20/env18 source control, absent from our110pilot and official
3,000eval routes:40packed steps/75raw frames, CRC/source stats verified, raw
expert reconstruction passes. Preserve future-history flags and version mismatch.
Viewer: localhost8771/openfly_execution.html (recorded reconstruction, no model
rollout). Sixroutes/237previews/452browser checks;33focused tests pass.
User granted HF simulator access; authenticated download now allowed. env18 scene
285,821,005bytes verified by LFS SHA256 and ZIP CRC, extracted under D:; first
whole-file response was incomplete. WSL22.04 supports CUDA but Vulkan is software llvmpipe;
21small graphics packages added, no upgrade/signature bypass. Next finish asset
verification/extraction and test real rendering before model-controlled navigation.
No new training/inference, AWS spending, baseline/index/split changes. D150 code
and data are separate from the architecture session; protected seeds unchanged.

## D149 drone-only literature audit complete

Read docs/research/vla_results_audit_20260919/REPORT.md. Fifteen aerial learned
action architecture papers, three aerial benchmarks and one dialogue boundary case;
31 screened candidates. No manipulation-only model in the architecture count.
Current OpenFly v7 SR is34.3% seen/22.6% unseen; old D146-D148 citations use v6.
HF model last update2025-08-29 predates v7; checkpoint-paper mapping unresolved.
Do not rank flight capability from our action agreement. Next gate remains exact
source calibration, expert playback and paired source-faithful closed-loop tests.
User review page: localhost8771/drone_vla_research.html. No new model runs or spend.

## D148 complete-route / original training-record investigation

Read reports/vla_openfly_routes_20260919/REPORT.md and openfly_routes.html.
D147's global vlnv11 decoder is NOT validated: exact original vlnv1 campus tokens
score12/15 directions /15 valid with source statistics, but0 valid with vlnv11.
Constant horizontal up/down dimensions become spurious1/1 under vertical stats.
Added source-statistics guard and regression; preserve old results as historical.
Two actual packed TRAIN records have verified source profiles: campus12/15,
altitude7/19 raw-interface or10/19 training-interface direction; all outputs valid.
Actual future-image history confirmed in4/34 steps; removing it changes no tokens
on these two samples. Packed/current versions differ in6m/3m labels, STOP repeats,
phase tags and instruction. No automatic relabeling or future leakage adopted.
Three full dev routes105rawframes/43decisions,274OpenFly calls and43Qwen calls
complete. Qwen10/43. Both raw-route decoder views remain explicitly provisional;
no source-faithful closed-loop OpenFly benchmark has been reproduced.
Next trace exact raw-route to RLDS-subset normalization, then bounded real-renderer
closed-loop evaluation. No training/GPU jobs active, AWS spend or split changes.

## D147 repairs and rerun complete

Read reports/vla_openfly_repair_20260918/REPORT.md and openfly_repair.html.
Strict decoder now rejects unsupported action sets; explicit vlnv11 adapter
covers vertical actions, but the checkpoint's historical calibration is unverified.
Corrected macro start frames; separate1639-row verified manifest keeps88/22 routes.
All100226 TRAIN schemas audited:9728 routes use climb/descent phase tags, with
STOP before descent;8160 recorded STOPs differ from final position by over20m.
Do not treat mission STOP and later descent endpoint as the same navigation goal.
Fresh matched72 direction counts: OpenFly20, Smol25620, Smol50021, Qwen24.
Six unquantized BF16 checks match NF4 token-for-token; nine regression tests and
72-case/288-output debugger checks pass. All GPU jobs ended, no training/AWS.
Old data, baselines, splits and held-out seeds remain unchanged.

## D146 investigation - D145 ranking is not validated

Read reports/vla_openfly_forensics_20260918/REPORT.md and openfly_forensics.html.
vlnv1 forces up/down outputs to zero:24/72 targets unreachable. Labels and
source frames passed independent checks. Prompt/history pooling diagnostics
failed to rescue the score. Verify checkpoint normalization/history mapping
and native macro-action evaluation before further training or model ranking.
Historical scores remain intact; no baseline/split changes or AWS spending.

## D145 complete - released openfly_vla comparison

Read reports/vla_openfly_same_panel_20260918/REPORT.md and
localhost8771/openfly_same_panel.html. Same 72 D144 native cases, released NF4
model with vlnv1/raw-instruction protocol: 18/72 direction agreement, 8/72 exact
primitive; 39 forward9m outputs and 13 invalid codebook vectors. Do not silently
convert unknown vectors to STOP. These official TRAIN routes are held out from
our adapters but potentially seen by the released model. No equal-unseen or
published-benchmark claim. No new training or flights, AWS or split changes.
Use openfly_vla for the model and openfly_vla data for the dataset in the UI.

## D144 complete - joint OpenFly/local three-model pilot

All three local runs completed 400 updates, four reload checks, 100 held-out
predictions and two audited local flights per model. No training job remains active.
Read reports/vla_joint_openfly_20260917/REPORT.md, completion_audit.json and
dashboard_final_check.json; live review: localhost8771/joint_openfly.html.
Smol256/Smol500/Qwen native exact results: 18/72, 16/72, 17/72; always-forward
reference: 12/72. Qwen base: 16/72. All six flights failed: Smol256 held until
timeout, Smol500 moved but timed out, Qwen stopped early at 2.097/0.432 m.
Native validation worsens after the measured 100-update checkpoint for all models.
Do not infer longer training or real-world readiness from falling training loss.

Data: 110 official TRAIN routes (88 train/22 dev), 2929/815 native decisions,
plus unchanged 1156/300 local examples. Eight inconsistent motion labels excluded.
Protected seeds and all 3000 official evaluation route IDs excluded. Keep distinct
contracts: OpenFly 3 m/30-degree actions and local FRD velocity JSON. Never invent
velocity labels from OpenFly primitives. Actual unique exposure: 592 native and
790 local examples per model. This is not a full benchmark result.

Final audits verify 1200 updates, 600 raw predictions, 12 reload spots and six
flights; browser checks all 100 cases and 300 final answers. Baseline fingerprints
are unchanged. Adapters remain in D:/drone_vla_pilot/runs/ under
{smol256,smol500,qwen}_joint_20260917_a. No AWS spending.
The Windows dashboard-lock interruption/recovery is preserved in recovery.json;
the completed Smol256 adapter was reused, not retrained.

Next isolate visual/history and mission-phase learning on training-only data,
then freeze a follow-up with broader unique route coverage. Keep baselines,
validation splits and protected seeds 1-40/1060-1064 untouched. No new run queued.

## D142 complete - native OpenFly pipeline passes, generalization fails

No training/GPU job remains active. Read reports/vla_openfly_train_20260917/REPORT.md
and localhost8771/openfly_training.html (recorded source flights, not model rollouts).
Smol500BF16/r8 native-ID pilot:8/8memorization;fresh160updates =>18/171dev exact,
macro.149 vsmajority113/171/macro.167;blankimages11/171(allSTOP),26falseSTOPs.
Both adapters saved onD:/drone_vla_pilot/runs/smol500_openfly_native_20260917_a;
fourreloadspots match;960exposures source/split/class-mixture audited. No AWS.
D141 expandedSmol500/Qwen400updates andfourlocalflights also complete;allflightsfail.
OpenFly old12/51coarse score becomes29/51 when SAME tokens re-decoded with released
vlnv1normalization;turns0/12. Post-hoc sensitivity, not newnativebenchmark result.
OfficialTRAIN22routes/258train/171dev isolated fromall3000officialevaltrajectories.
Rawmotion910/911consistent;onezero-yawturnflagged. Compressedannotation gaps are
not nativeaction durations. Do not convert tovelocities or claimphysicalcontrol.
Next reconcile atomic-vs-macroalignment, preserve these frozen splits/results,
then broaden train/devcoverage (includingverticaldev andrealflightdomains).
No fulltraining/sweep warranted yet;oldFRDbaselines andprotectedseeds unchanged.

## OpenFly local probe and dashboard fixes - D140 (2026-09-17)

User requested OpenFly download/comparison. Verified15.086GB snapshot on D:;
NF4 loads on RTX4060 with5.858GB peak allocated.32actual predictions on16old
visual VAL cases:official training template alwaysright8/16,modelcard alwaysSTOP.
Read reports/vla_openfly_20260917/REPORT.md and localhost8771/openfly_comparison.html.
All jobs finished. No OpenFly fullflight/nativebenchmark result claimed. Next
explicitly reconcile native primitive amplitude/normalization then compare flights;
never map unknown vector toSTOP. Separate venv_openfly preserves old environments.
Original/Expanded flight names and actualexecution counters fixed,sourceIDs intact.
No AWS/baseline/split changes. C5 is OnFly-inspired,not OpenFly checkpoint.

## Matched balanced comparison complete - D139 (2026-09-17)

Smol256 only,two fresh matched400-update/1600-exposure runs;all jobs/evaluations
finished. Read reports/vla_balanced_comparison_20260917/REPORT.md and
localhost8771/balanced_comparison.html. Expanded data improves newVAL loss
0.4835->0.4012 and STOP0/6->5/6,but false STOP1->8/128 and visual directions
stay8/16old,32/64new. Both adapters0/2flights:control premature STOP near1.94/
1.39m;expanded holds atstart8.54m orSTOPs immediately8.00m. Both pilot gatesfail.
Exact matched initialization/baseline,raw-output/schedule/reload audits pass;
121flight calls/463controls plus128visual controls replay audited;388prediction
browser checks and14flight source-time checks pass. Loss plots verified.
Next isolate visual-only learning and HOLD/STOP/3D completion contrasts before
scaling;D127 external/real/task coverage and real-time controller gates remain.
Do not repeat finished runs or infer500/Qwen were trained in D139. Existing
architecture baselines,validation/protected seeds and earlier evidence preserved.
No AWS spending or physical flight. Latest goal has completed its comparison,
not achieved a deployment-ready VLA.

## Expanded local data and mixed batches ready - D138 (2026-09-17)

Latest user requests expansion and mixing within every batch. Completed additive
local dataset at D:/drone_vla_pilot/data/local_expanded_20260917_v4:1156TRAIN,
300VAL,all original84VAL untouched. Four-task effective batches use microbatch1
and accumulation4;two real Smol256 updates pass,53 tests pass. No full new model
experiment yet. Read reports/vla_local_expanded_20260917_v4/REPORT.md.
Viewer localhost8771/expanded_data.html includes exact targets and20 teacher
flight replays. Next freeze matched balanced-existing/expanded short comparison;
original/new validation separate. This supersedes the narrower immediate-next
instruction below in accordance with the user's expansion request. No new domains,
AWS or physical flights. Do not admit failed v1/v2/v3 data attempts.

## Smol capacity/duration follow-up complete - D137 (2026-09-17)

Both image-only256M/500M pass16/16 tiny memorization and reload. Same local252
TRAIN/84VAL,400versus1200updates,unchangeddata/sampling/LoRA.256 resumes its
preserved400adapter;500fresh. Comparable eval-mode losses reveal overfitting:
TRAIN falls while finalVAL rises forboth. Both still8/16visualdirection,0/8
instruction/color-swappairs and0/2STOP. Some coordinateerrors improve;do not
conclude everymetric worsens orparametercount alone iscausal. Both gatesfail.
Schedules and4finalreloadspots checked;32savedvisual segments/128controls and
176browser assertions pass. No newclosed-loop flightclaim. All jobs finished.
Read reports/vla_smol_duration_20260917/REPORT.md andlocalhost8771/smol_duration.html.
Next freeze visual-only TRAIN overfit,then separate class-balance test. Keep
externaldata expansionD127 forlater. Preserve originals,architecture session,
validationgroups andprotectedseeds1-40/1060-1064. NoAWS/physicalflightwork.

## Active cached Smol256 / mixed local experiment - D136 (2026-09-17)

Use this isolated VLA worktree only; the architecture session is separate.
Cached image-only SmolVLM-256M passes16/16 tiny memorization/reload gate.
Fresh Smol256 and Qwen4B adapters then completed identical400-update schedules
on252 existing TRAIN rows (204coordinate+48visual),84 original VAL rows.
Both emit28/28 valid outputs but fail the full pilot gate (both tested STOPs
missed). Smol visual direction8/16, constant clockwise;Qwen16/16 and both
instruction/color-swap pair scores8/8. Exact-source0.2s execution confirms
8/16 versus16/16 target-error reductions.176 debugger assertions pass.
Both mixed coordinate adapters0/2complete;Qwen approaches then holds outside
goals,Smol never translates.302calls/1202controls and20flight browser checks
pass. Preserve prior tiny Qwen1/2success as a regression reference.
Evidence: reports/vla_smol_mixed_20260917/REPORT.md; raw data/weights on D:.
Local review: localhost8771/local_mixed_predictions.html. Loss plots accompany
report. Do not equate lower loss with control success or infer broad transfer.
Next isolate visual overfit and sparse STOP/HOLD failures on local data before
external imports. Preserve current validation groups; no tuning on seeds1-40.
External sim and real-flight data remain required later under D127. No AWS,
paid resources, physical flights or architecture baseline edits authorized.

## Active FRD follow-up - D131-D134 (2026-09-16)

Work stays isolated on codex/vla-aws-pilot-20260916. Heading-level
forward/right/down and clockwise yaw use direct_velocity_heading_frd_v2;
old FLU schema/data/checkpoints remain unchanged. D134 passes tiny TRAIN gate:
16/16 exact after400 total FRD updates, reload identical,4.617GB peak allocation.
This establishes memorization only; autoregressive latency remains about4s
against0.2s action horizon. No realtime/real-world readiness claim.

D133 adds64 audited visible-pillar yaw segments (48train/16val), with image and
instruction contrast pairs. No model trained on those pairs yet. D127 audited
5real+5external-simulator complete preview sequences,531frames;ZERO external
action-training episodes admitted, pending license/calibration/control/splits.
Source playback: localhost8771/data_expansion.html.77focused tests pass.
Reports: reports/vla_frd_followup_20260916. Raw datasets/checkpoints on D:.
Matched offline validation on1400/1405:zero-shot0/2,trained1/2complete.
186calls/741controls pass exact replay and12browser checks. Review
localhost8771/frd_comparison.html and REPORT.md before extending training.
Preserve seeds1-40 and exclude1060-1064 from training. NoAWS/paid resources,
physical flights, baseline changes or interference with the architecture session.

## Actual Qwen pilot - D-130 (2026-09-16)

Actual Qwen3-VL4B NF4/r8 LoRA completed200 updates locally in269s at4.47GB
peak PyTorch allocation.16/16 strict JSON,9/16 exact,0/4 STOP: overfit gate FAILS.
Adapter save/reload identical16/16. Median generation4.34s vs0.2s action horizon.
Reports in reports/vla_local_pilot_20260916; weights/data isolated on D:.
Three capped offline model-flight diagnostics complete:all timeout (2.95m,
1.75m,8.00m).150 exact source images/prompts and600 decoded controls pass replay.
Simulation explicitly pauses during inference. Review local8771/model_flights.html
and reports/vla_local_pilot_20260916/REPORT.md.61 focused tests pass.
Do not infer real-time/visual/transfer capability.
No longer training or AWS launch without revisiting the failed gate.

## VLA observable fixture - D-129 (2026-09-16)

Eight teacher flights1400-1407 recorded on D:/drone_vla_pilot/data/
public_goal_fixture_20260916_v1.272 samples,204train/68val; full replay/source/
executed-label checks pass. Reports: reports/vla_local_pilot_20260916.
Teacher debugger is generated teacher_flights.html; explicitly no model calls.
This coordinate/odometry task does not require vision. Model overfit remains next;
Qwen4B pinned public base downloading to D:, isolated venv_qwen installed.
No AWS/paid work. D127 sim/real expansion remains mandatory.

## VLA local execution contract - D-128 (2026-09-16)

Active user goal: local VLA correctness pilot while user away; no AWS/paid work.
New additive direct_velocity_yaw_level_v1 passes52 focused tests,4096 command
samples and128 matched controller/router/physics segments. Maxpositiondrift
7.35mm/0.2s; explicit hold/STOP and expiry pass. See
reports/vla_local_pilot_20260916/contract_execution.json. The prior draft is now
validated at the component level, superseding D126's draft-only status.
Next collect synchronized raw controls, poses and images with observable
terminal criteria; model training and inference remain undone. Source yaw fixes
a level forward/left/up frame, not full roll/pitch aircraft-body coordinates.
Continue D127 broader sim/real data plan. Do not touch the architecture session.

## Required VLA data expansion - D-127 (2026-09-16)

Read docs/research/VLA_DATA_EXPANSION_PLAN.md. User explicitly requires both
additional simulation domains and real-flight data; the red-tower corpus is only
a pipeline fixture. Validate small source samples before bulk import. Freeze
task/domain/group splits, preserve seeds1-40 and exclude1060-1064 from training.
Local overfit success cannot complete the broader VLA goal. No new data imported
or training/cloud job started by this planning update.

## Local-first VLA data review - D-126 (2026-09-16)

User defers AWS launch: validate locally first. No training has run. The current
100-episode corpus has one instruction, one synthetic simulator, no real-flight
or external-simulator data, and a simulator-truth-derived coarse goal bearing.
Structural audit still passes; semantic training gate remains closed.
Original camera/label playback: reports/vla_dataset_review_20260916/REPORT.md,
localhost8771/viewer.html. All4765 embedded JPEGs match source bytes;12 exact
browser frame/label/time checks, split filters and playback pass. Collector saved
no original full pose/control logs; do not call this a live/3D/predicted flight.
New direct_vla_contract.py is an unvalidated, unused draft from the prior turn.
Next synchronize raw controls/poses/images and validate terminal observability.
Tiny surrogate training cannot certify Qwen/QLoRA fit or adapter correctness.
Architecture-session files/shared services remain untouched.

## Storage correction - D-125 (2026-09-16)

100 GB was only a tiny-pilot disk, not the full VLA dataset budget. Published
files across five candidate corpora/simulator repositories total 861.4 GB before
extraction/caches. See storage_inventory.json and the appended D-125 plan.
Propose 100 GiB root plus staged 512 GiB data; provisional 2 TiB data for broader
use after measuring expansion. Root+2 TiB costs about179.57 USD/month while
provisioned; old5USD proposal does not cover a day plus GPU at that size.
No new spend or machine approved. Screenshot's PyTorch2.13/Ubuntu26.04 image
family exists in officialAWS docs; isolated training environment still untested.

## VLA AWS pilot preparation - D-123/D-124 (2026-09-16)

This isolated branch recovers the VLA plan and audits local data; it does not
replace the C5 work below. Read docs/research/VLA_AWS_PILOT_20260916.md.
Recommend one g6.2xlarge (24 GB L4/32 GiB RAM, Stockholm public Linux compute
1.03688 USD/hour). Actual AWS host/quota/credits remain unknown. Console tool
fails during Windows sandbox startup; no SSH/AWS profile is configured. User
requests exact machine approval before launch and measured-budget approval
before training. No machine was launched; no training or spend was performed.
Strict audit/export passes with 4,765 samples and unchanged 80/20 seed split;
97 focused tests pass. Data is not training-ready: 35/100 episodes have no LAND,
codec changes teacher hold/speed/yaw, and all data share one task/domain.
Prompt-drift claim was a Windows-decoding false alarm; UTF-8 prompts match.
Do not treat the old three-epoch script as the approved pilot. Do not train on
1-40 or pilot dev evaluation 1060-1064. Original baselines/actions untouched.
Next: restore AWS access, validate teacher execution and terminal observability,
then separately approve a bounded overfit/short-run and exact debugger evaluation.

## Latest: D-122 continuation succeeds (2026-09-16)

Read reports/continuation_20260916/REPORT.md and STATE.json FIRST. Exact cached
prefix verified before one fresh local continuation. No navigation changes.
Arrival radius entered94.5s; monitorSTOP97.2s; final0.9363m, speed0.05176m/s,
zero collisions. Task criterion passes; sustained hover is not demonstrated.
Original90s timeout preserved; successful trajectory has a120s maximum budget.
All1800 prefix controls/135requests match; final1945poses/97policy+49monitorimages
match.10UIseeks/2playbacks and terminal/sourcecamera inspected.8harness tests pass.
13freshattempts=12complete+1cancelled;134cachedprefix responses are not newcalls.
Next matched target-commitment on/off, same model/hardware/budget/seed schedule;
no reliability or causal architecture claim yet. D121 stays a named extension.
Dedicated11435 unloaded/stopped;8766 debugger retained;shared11434/Valley untouched.
No additional flight scheduled, no automation restart. Commit each change.

## Autonomous recovery batch complete — D-116 through D-121 (2026-09-15)

Read reports/recovery_cycle_20260915/REPORT.md, cycle3/REPORT.md and STATE.json FIRST.
Three of four maximum flights used; all audited, no automatic launch remains.
D116 handoff works but timeout. D117 VLM-selected viewpoint return restores red,
then occlusion recurs; timeout. D121 named target-commitment extension clears the
obstacle, red reappears by sampled74s and 75–90s approach is monotonic. Still timeout:
closest/final4.64661m, zero collisions, no STOP. 134 completed calls +1 cancellation.
Controls differ from baseline already1s before first lease13s, with CPU/GPU placement
different. Better distance is NOT an isolated causal architecture comparison.
Lease audit passes: original source timestamps, nonrenewing20s deadlines,419 commands
older than4s (max18s),13 LOSTyaw deferrals.420 full-suite +20 focused tests passed.
All1800 poses/89 inputs match;66 UI seeks/2 playbacks plus7 final captures reviewed.
Keep native profiles unchanged. D121 is neither native OnFly nor D117 return-to-view.
D120 correction: D118/D119 probe history used control cadence,not exact live memory;
true35.95s latesthistory34.95s. Withdraw8.1s livegap claim; do not reuse it.
NEXT offline: exact cached-request replay/checkpoint validation before a separately
frozen bounded continuation for arrival/STOP beyond90s. Preserve90s failed benchmark.
Matched inference placement/repeated seeds required for causal comparisons.
Dedicated11435 unloaded/stopped;8766 debugger retained;shared11434/Valley untouched.
No fourth flight: fullCPU trial takes43min, beyond remaining autonomous window.
All changes committed independently; no cloud/key reads/reinstalls.15 saved-framecalls.

## Latest: Qwen4 six-frame gate + one clutter flight complete - D-115

Read reports/qwen4_validation_20260915/FLIGHT_REPORT.md. Six new image checks pass;
one flight times out, closest13.75 m versus Gemma22.58 m, zero collisions.
Qwen4 profile is diagnostic, not a general replacement. Recovery fires but expires
10.314 degrees short; completing the heading offline still does NOT reveal target.
Next: isolate reacquisition/expiry and positional-view recovery; do not blindly
extend the timer or attribute a new search mechanism to a published architecture.
Flight debugger localhost8766/qwen4_clutter.html, key interval33.95-40 s.
All1800 poses/89 source images match. Dedicated11435 stopped; shared11434 untouched.
D-114 new-image gate below is completed by this entry. No extra flight scheduled.

## Local model inventory change (2026-09-14)

User requested deletion of qwen3-vl:8b, qwen3-vl:2b, qwen3.5:4b,
qwen3.5:2b and moondream:latest. All five removed and absence verified.
Qwen3-VL4B and Gemma retained; other unlisted models untouched. D-114
results/configurations are historical evidence, not proof those weights are
still installed. Do not automatically reinstall removed models for routine work.

## Latest: seven local VLM comparison complete - D-114 (2026-09-14)

42 attempts:36 replies plus6 SmolVLM2 package HTTP400 multimodal-unsupported errors.
Same D-113 three scenes/grid+box, no retries/cloud/flights. Qwen3-VL4B and8B pass
both formats3/3;2B boxes3/3,grid2/3. Positive boxIoU2B0.5946,4B0.7765,8B0.7145
vs savedGemma0.0502. Qwen3.5 2B/4B miss positivebox (IoU0/0.0354). Moondream
allgridwrong/allboxinvalid. No architecture/runtime promotion or general planning claim.
Read reports/local_vlm_comparison_20260914/REPORT.md and dashboard
localhost8766/local_vlm_comparison.html. All42 image/request identities checked,
36 CPU-only residencies,48 UIpanels. Separate11435server stopped after unloading;
shared11434 untouched,reachable. Full modelIDs/digests and rawchannels preserved.
Candidate:Qwen3-VL4B,with2Bboxes as smaller option; next new independent image gate,
not more tuning on these3cases. CPU latencies are not flight benchmarks. No call scheduled.

## Latest: grid/box localization probe complete - D-113 (2026-09-14)

Six local calls: grid correct B2 on visible target, false C3/B1 on absent images;
box correctly rejects absences, but visible box IoU0.05024 and center on gray neighbor.
Neither ready/promoted. No runtime changes,cloud,retries or flights. Exact original
and grid inputs,raw responses and frozen criteria retained. Read
reports/localization_formats_20260914/REPORT.md; localhost8766/localization_formats.html.
Do not combine results post hoc and claim success. One positive/two negatives do not
establish reliability. Presence and localization need independent-case validation;
no further call or flight is scheduled. Prior D-112 next-step probe is now complete.

## Latest: saved-frame pointing failure isolated - D-112 (2026-09-14)

Six paired local Gemma calls complete on3 frozen sources. Both prompts name visible
red tower but return(499,499) on gray neighbor. Hidden target: candidate corrects
label but points at wall; close wall: no hold. All6 selected points on gray faces.
Actual policy lift/reprojection preserves pixel<=3.18e-14 px.3 RGB sources and1,040
saved prefix poses match. No runtime changes,promotion,cloud or new flight.
Read reports/passage_choice_20260914/REPORT.md; localhost8766/passage_choice.html.
Candidate hold exists only in diagnostic schema; do not treat as implemented flight
behavior. Next offline pointing representation (box/labeled region), not SUPER
clearance changes. Three selected cases do not establish general incapacity.

## Latest: return-to-clutter diagnostic failed; transport verified - D-111

Two new seed1061 flights complete: corrected integration timeout final37.906 m;
matched policy attribute-contract trial timeout final67.845 m. Do not promote either
as navigation improvement. Gray/green false target bindings observed in exact source
images despite red mission; attribute guard removes labels but alternatives still
fail to search. Original narrow-gap case not reached; no execution-incapacity claim.
RGB/BGR concern: actual client encoding/request construction preserves224x224 RGB PNG
bytes; red remains(205,46,46). Server preprocessing not examined. Zero network for
transport test.33 tests,5,400 exact poses,178 source images,15 seeks/3 playbacks pass.
271 completed local Gemma incl3 probes,+2 cancellations. No runtime edits or third run.
Read reports/clutter_stable_20260914/REPORT.md. Dashboard localhost8766/clutter_stable.html.
Next saved-frame exploration contract; retain successful hover profile from D-110.

## Latest: hover departure fixed, two bounded passes - D-110 (2026-09-14)

New c5_hover_stable_gemma_dev keeps heading near translation goal, fixes the approach
line to initial onboard frame, and uses coherent live hover completion. 1062 passes
15.2 s/1.002 m/6.1 s hover;1060 passes13.2 s/1.002 m/4.1 s hover. No contact/collision.
442 tests pass; old1,200-pose component probe and1,770 dashboard poses match;15 new
monitor images match exact source.43 Gemma calls+2 cancellations,zero cloud.
Read reports/hover_stable_20260914/REPORT.md. Runtime commits dc869fa,b1d8a0b.
Dashboard http://127.0.0.1:8766/hover_stable.html; Valley owns8765, do not stop it.
Old profiles/results preserved. Same-scene repair, not a planning/generalization
result; completion remains conservative. No further flight active or scheduled.

## Latest: hover repeat failure diagnosed — D-109 (2026-09-14)

Two user-requested unchanged repeats complete: 1060 passes,1062 times out. Same scene;
2/3 including D-108 success is repeatability evidence only, not reliable completion.
Read reports/hover_repeat_20260914/REPORT.md and DEPARTURE_AUDIT.json. Failed flight
physically hovers >8 s but monitor misses completion: initial 1.95 s gate then changing
body-pixel anchor exceeds 0.35 m cross-track despite stable drone position. Tiny
translation errors drive +/-0.4 yaw; obs380/18.95 s loses target, exploration command
executes at20 s and departs. No scheduler race proven, no additional run or fix.
231 source/config hashes unchanged; 106 new Gemma calls +2 cancellations; no cloud.
Three replays/1,650 poses and exact source images verified; dashboard hover_repeat.html.
Next diagnose heading hold and stable/temporally coherent hover reference offline.

## Latest: explicit approach-hover cycle completed — D-108 (2026-09-13)

User authorized autonomous run/debug/fix without per-step confirmation. Latest
reports/hover_cycle_20260913/REPORT.md and dashboard reports/debugger/hover_cycle.html.
Four new flights; final c5_hover_level_20260913_s1061 PASSES at 11.2 s, 1.003 m,
2.1 s visible slow hover, no contact/collision. Preserved failures: old radius stop,
close-up identity loss, target-pixel altitude/reference-line drift. New named variant
uses standoff, grounded pixel choices, reference/current visual grounding, initial
onboard altitude and continuous hover validator. Do not call it native paper OnFly.
433 tests pass; 1,835 replay poses, 12 browser seeks/four playbacks checked. Raw final
speed violation 1 is 4.44e-16 m/s roundoff; evidence retained. No flight active.
One fixture only; AerialClaw search/order and broader planning still unresolved.

## Latest: targeted contracts and one verified arrival fix — D-107 (2026-09-13)

Read `reports/targeted_contracts_20260913/REPORT.md`; dashboard:
`reports/debugger/targeted_contracts.html`. Five new flights including retained failures.
Final C5 arrival-window variant PASSES at 13.2 s / 0.371 m, no collisions/violations:
confirmed stationary RGB-D target survives view loss; 4 s window includes return-time
age, live range/age check retained. Initial 3 s trial failed at 3.25 s response age.
C1 inspected search removes the old scan gate defect but model repeats detection
without rotating; timeout. Ordered visual tools and onboard dwell/order validation
implemented. Initial ordered prompt retained passive-detector strategy (confounded);
final requested-perception prompt detects/reaches red and completes first dwell,
but repeats red goto and never queries blue. Calls 4–6 explicitly show first complete.
Do not claim search/ordered success or model incapacity; remaining inherited single-label
prompt context needs audit. No more flight active/scheduled; five-flight cap exhausted.
Legacy profiles remain selectable; new mechanisms are named opt-in development variants.
All failures, exact evidence, offline tests and dashboard checks are documented in D-107.

## Latest: frozen 24-cell post-repair comparison — D-106 (2026-09-13)

Read `reports/frozen_capability_20260913/FINDINGS.md`; dashboard:
`reports/debugger/frozen_capability.html`. All 24 fresh seed-1061 flights complete,
no runtime/config changes or retries: C0 6/8 (privileged), C1 2/8 raw (coordinate
and visible target pass; five cells remain explicitly text-only/integration-limited),
C5 0/8 with partial task progress. This is NOT an architecture ranking.
Corrected C1 search is now flight-tested and fails: target visible during rotation
at 10 s, sole detector input at 21.95 s has no target; further model-requested scan
is rejected by inherited full-turn gate. Angular coverage is not inspected coverage.
OnFly reaches 0.335 m in visible task, but range sample 2.092 m fails arrival gate
and next image lacks target; no stop. Its isolated causal repair remains unresolved.
743 completed Gemma calls + 16 cancellations; no cloud. All 19,414 poses replay
exactly; 72 browser seeks / 24 playbacks / 24 closest-approach inspections pass.
Source/config hashes and all manifests match the preflight freeze. See per-cell
failure classifications and next isolated checks in FINDINGS.md. Preserve this batch;
no further flight active/scheduled. Older D-105 'offline-only search' status is superseded.

## Latest: AerialClaw coordinate/visual skill repair - D-105 (2026-09-13)

Read `reports/aerialclaw_tools_20260913/REPORT.md`. Coordinate completion now passes
at 26.0 sim s: policy and stop runtime use the explicit public ENU instruction plus
live odometry, without demanding visual labels. New requested visual-tool profile
passes visible target at 35.7 sim s, final 1.415 m, zero collisions/violations: 3 text
planning calls + 1 RGB detection. No continuous image-to-waypoint policy; SUPER unchanged.
Strict selected-pixel detection failed before opt-in 3% local depth refinement.
Search remains unresolved: legacy advice caused scan/coverage with zero detection calls.
An intended-strategy run is INVALID SETUP: failed code insertion/test did not stop its
PowerShell chain. Preserved; actual advice insertion fixed and offline-tested afterward.
Do not claim c1_visual_search_gemma_dev has passed a flight. Explicit exit-code gates
are required before launching from command chains. No further run is active/scheduled.
Five new flights total (including invalid setup): 21 completed calls + 5 boundary
cancellations; one extra unsuccessful saved-frame bbox probe. Gemma only, no cloud.
406 unit/contract tests pass; seven exact replays, 21 browser snapshots/7 playbacks pass.
Dashboard: `reports/debugger/aerialclaw_tools.html`. Next one bounded search validation
of corrected advice; then task-level reasoning only after inspecting actual behavior.
New visual profiles currently support one declared public object query; multi-stage
and dynamic semantics remain open. Preserve D-104 and all D-105 failures.

## Latest: 24 capability flights completed - D-104 (2026-09-12)

Read `reports/capability_screen_20260912/FINDINGS.md` before quoting scores.
One seed 1061 per scenario/architecture: C0 6/8, C1 0/8, C5 0/8. No runtime errors.
C1 text-only Gemma profile has no visual input; known-coordinate arrival succeeds
physically but done is rejected by exact-label completion evidence, then stop is stale.
C5 reaches 0.335 m from visible target, then departs without monitor stop. It also
completes red visit and correct gate crossing. Do not call all timeouts planning failures.
Camera pitch is calibrated; C5 uses existing generic ground monitor, no color guard.
C1/C5 latency is inherited and unmatched. Zero collisions; C5 has constraint violations.
745 completed Gemma calls + 15 boundary cancellations; no cloud or further flights.
All 24 replays match; 72 browser snapshots + 24 playback checks pass.
Dashboard: `reports/debugger/capability_screen.html`. No run active or scheduled.
Next: saved-evidence diagnosis of C1 coordinate completion and C5 arrival/stop;
C1 visual integration remains unresolved. Keep this batch frozen; no automatic sweep.

## Latest: eight capability scenarios implemented — D-103 (2026-09-12)

User authorized one first scenario in each agreed category. See
`docs/CAPABILITY_SCENARIOS.md` and `reports/capability_scenarios_20260912/REPORT.md`.
Eight capability_* environments use the shared simulator with private task scoring;
normal observations have no semantic-hit answers. Ordered visits, branch choice,
closure and sustained tracking are evaluated explicitly. Legacy scoring is unchanged.
Eight scripted geometry fixtures pass with zero collisions, plus C0/SUPER known-goal
integration passes at 5.75 s. These are not real-model capability results.
Dashboard: `reports/debugger/capability_scenarios.html`; C0 has its own linked page.
No inference budget used, no training, no held-out run, no next flight scheduled.
Latest research design is ASP-UAV_Final_Research_Design.pdf (external path in task doc):
nine architecture conditions, eight capability regimes. Old concise PDF is earlier.
D-102 gate repair remains open; no policy behavior was changed in D-103.

## Latest: adaptive-plan flight visually diagnosed — D-102 (2026-09-12)

Read `reports/adaptive_plan_flights_20260912/REPORT.md`; dashboard:
`reports/debugger/adaptive_plan_comparison.html`. New seed-1061 flight timed out
at 90 s, zero collisions, closest/final 23.995 m; stops moving near 23.75 s.
Gate rejects 71/89 proposals from 19 s, only 18 reach SUPER. Model receives failure
feedback but keeps s1: 32 identical center moves, then 57 retains of a rejected point.
Copied historical SUPER finds full known-free paths to the exact rejected goals at
19 and 32 s (641 poses/32 gates/18 plans replay-match). Do not call this physical
execution success or a VLM-only failure. No runtime/config change, second full flight
or further run scheduled. Next targeted change: align acceptance criteria with SUPER,
then separately test explicit rejected/accepted goal state and retain recovery.
User authorized flying and dashboard diagnosis; that bounded work is complete.
One preflight plus 134 completed flight calls, one boundary cancellation; Gemma only.
Do not repeat an unchanged stalled run or tune clearance without a case-specific test.

## Latest: VLM-authored planner implemented; offline checks pass — D-101 (2026-09-12)

Read `reports/adaptive_visual_plan_20260912/REPORT.md` and
`docs/research/vlm_authored_planning_20260912/REPORT.md`. New policy/config:
`adaptive_visual_plan` / `vlm_adaptive_plan_gemma_dev`. VLM authors intermediate
objectives/order/points; explicit retain keeps an anchored world goal. Strict
output parsing, matched routing feedback and model plan/pose history are implemented.
Debugger shows plan, active objective, expected view, memory and original point source.
361 unit/contract tests and lint pass; 8 browser fixture checks pass. No real model
calls or flights yet. Next one bounded saved-frame Gemma/schema check before any
flight; no run scheduled. Use corrected-depth environment and development seeds.
New component-level MapGPT/SPF adaptation, not full paper reproduction or isolated
planning ablation. No supplied graph; forward-camera/backtracking limits remain.
SPF travel and endpoint verifier differ from C5; fixed simulated charge is not wall
latency. Shared SUPER/controller/monitor remain identical, tested. No GT/semantic_hits
in new policy input; no secret reads, cloud retries, model swaps or held-out runs.
D-100 next direction superseded, source audit preserved.

## Latest: drone_control graph audit and comparison specified — D-100 (2026-09-12)

Read `docs/research/drone_control_graph_comparison_20260912/REPORT.md` before the
next architecture implementation. User authorized inspecting drone_control and
defining a comparison, now complete. The older graph path chooses nodes classically;
a separate VLM region menu has optional frontiers OFF by default and unstable IDs.
Do not conflate them or claim their historical success is a matched planning result.
Proposed primary contrast: identical graph/candidates/perception/execution, classical
versus Gemma selector. C5 remains frozen end-to-end context. Next implementation unit:
typed candidate snapshots, stable IDs and a sensor-derived map adapter, displayed in
the debugger and checked offline. Shared target grounding remains an explicit open
gate. Keep SUPER and task fixed, no semantic_hits/truth shortcut, no source arena
constants or full AirSim stack transplant. Design only: no runtime changes, model
calls or flights in this audit; no new flight scheduled. Source hashes and ranges
recorded; drone_control was read-only.

## Latest: two additional corrected-depth flights completed — D-99 (2026-09-12)

User authorized exactly two more flights. Seeds 1060 and 1062 both timed out
at 90 s with zero collisions. Closest/final target distances: 1060 26.24/59.27 m;
1062 21.22/37.46 m. Same corrected-depth environment and guarded Gemma config
as D-98; all 268 completed new calls actually used local gemma4:e2b. No runtime
changes, cloud calls or adaptive tuning. Corrected-depth development total 0/3.
Read `reports/depth_renderer_two_runs_20260912/REPORT.md`; watch the updated
`reports/debugger/depth_fix_comparison.html` (two new flights, prior corrected
1061 and historical legacy 1061). All replays and browser checks pass; exact
requests/responses captured. No run remains active or scheduled. Next inspect
source-aligned decisions around approach/departure: 1060 closest at 24.50 s,
1062 at 39.45 s, prior corrected 1061 at 40 s. Keep the validated sensor repair;
do not infer a full failure cause from aggregate results or silently extend the
run budget. Rebuild comparison with `scripts/report_depth_fix_two_runs.py`.

## Latest: depth fixed; matched Gemma flight still fails — D-98 (2026-09-12)

Implemented `box_ray_v2` per-pixel box depth, validated against 1,146 saved
patch pixels. All 342 unit/contract tests pass. Historical default remains
`legacy_corner` for exact old-run replay. Use `grid_nav_onfly_depth_v2_dev`
for the corrected sensor in this investigation; architecture is unchanged.
One authorized Gemma seed-1061 flight timed out at 90 s: final 30.01 m versus
14.62 m original, closest 14.94 m versus 14.32 m, zero collisions. No navigation
improvement established; no run remains active or scheduled. All 134 completed
calls used local gemma4:e2b, with full debug capture. Read
`reports/depth_renderer_fix_20260912/REPORT.md`; watch
`reports/debugger/depth_fix_comparison.html`. Both trajectories replay exactly.
Next inspect source-aligned decisions around the new 40 s closest approach
and subsequent departure. Do not revert correct geometry merely to recover
an old score, infer model causality from one seed, or start an adaptive sweep.

## Latest: waypoint audit confirms depth defect — D-97 (2026-09-12)

Read `reports/waypoint_handoff_audit_20260912/REPORT.md`; inspect the source
pixel/depth/world-waypoint page at `reports/debugger/waypoint_handoff.html`.
At the disputed decision, box depth is 0.213 m but the selected camera ray
reaches the wall at 1.732 m. The renderer paints one off-screen corner depth
over the entire obstacle. Full replay matches 1,800 controls, 89 plans and 89
source depth images exactly. Selected pixels also lie on a foreground wall;
do not claim the VLM is exonerated. Goals during 32–41 s vary by only 0.116 m,
so large destination replacement is not supported as the cause in that phase.
Next: fix per-pixel sensor depth, preserve the historical renderer for old
replays, and verify the same saved pixels before a bounded flight comparison.
No runtime fix, model calls or new flight in this audit. Camera tests (2),
independent geometric checks, script lint and browser checks pass. No new
verifier or architecture variant is warranted by this result alone.

## Latest: fixed-destination SUPER test succeeds — D-96 (2026-09-12)

One user-authorized continuation from the exact guarded Gemma t=41.60 s state
reached a manual fixed waypoint in 38.10 s, collision-free. SUPER chose a wide
21.83 m detour around the right obstacle with unchanged settings. All 833 prior
controls/positions and all 41 historical plan records match exactly. This is
privileged local-stack evidence, not an autonomous benchmark or a VLM verdict.
Read `reports/super_passage_probe_20260912/REPORT.md` and inspect
`reports/debugger/super_passage_4160.html`. The original active waypoint was
only 0.378 m from the restored drone. Next inspect pixel/depth/world-waypoint
replacement together before choosing a fix. No new verifier, no inference,
no runtime change, no next run scheduled. The design permits named architecture
variants with frozen shared execution/observations, not silent reference changes.

## Latest: user-directed physical passage test — D-95 (2026-09-12)

User requested a manual crossing from guarded Gemma t=41.60 s / observation
833. Two probes restored exact pose, velocity and yaw. Straight at 82.05 degrees
collided after 9.85 s. Aiming 8.04 degrees right at the visible opening cleared
both obstacles in 19.50 s without collision, with 0.213 m sampled body-to-wall
gap. No VLM calls, model changes or runtime navigation fixes. These are
privileged physical diagnostics, never autonomous benchmark results.
Read `reports/passage_probe_20260912/REPORT.md` and watch
`reports/debugger/passage_4160.html` (portable source page also in the report
folder). Planner clearance is configured at 1.8 m; actual inferred occupancy and
route commitment were not reconstructed in these manual probes. Next inspect
that boundary at the user's specific state before choosing any navigation fix.
Do not reduce safety margins or claim a VLM root cause based on this probe.

## Latest: shared visual debugger ready — D-94 (2026-09-11)

User requested visibility before further navigation changes. Open
`reports/debugger/index.html`; guide: `docs/FLIGHT_DEBUGGER.md`.
Three existing seed-1061 flights are loaded: guarded Gemma failure, repaired
Gemma baseline failure and historical Qwen success. All 5,305 positions and
final distances match saved logs; all 396 decision sources match. No inference
or new navigation experiment was run. 335 unit/contract tests and browser checks pass.

Use `uavlab debugger RUN_DIR [RUN_DIR ...]` for zero-inference export; the older
`uavlab replay` command actually reruns inference. Old missing prompts/outputs
are labeled, camera/observer views are reconstructed, and code references are
current checkout unless an actual snapshot was captured. The exporter currently
supports grid3d without injected failures and rejects mismatched trajectories.

For the next separately authorized development run, append `--debug-capture`
with a fresh output directory (or `Orchestrator(..., debug_capture=True)`). It
preserves request prompts/images/schema, returned payload, failures, full paths
and actual code locations. Defaults remain unchanged. First inspect a shared
moment and agree on the observed mismatch; do not start another blind sweep.
Quota blocks, held-out restrictions and shared resident Gemma remain in force.

## Latest: bounded debugging completed — D-87–D-93 (2026-09-11)

Five adaptive Gemma flights on seed 1061 all timed out. No collisions or
premature stops; no variant promoted and active profile unchanged. Budget
exhausted; no run/model call remains scheduled. Read
`docs/research/c5_navigation_audit_20260910/AUTONOMOUS_DEBUG_20260911.md`.
Code/log/evaluation fixes and every result are committed; checkpoint 3147bd4.
D-92 corrects monitor scoring to the source image; earlier activation-frame
accuracies are superseded. Trial 4 has TP=3/FN=6/FP=0/TN=36. Saved-image
checks still miss a clear red target despite describing its rectangle.
Next: establish reliable positive/negative image grounding before another
navigation sweep. Do not promote stricter stopping as solved navigation.
323 unit/contract tests and focused lint pass. Keep Gemma resident, secrets
untouched, provider quota blocks and held-out seed restrictions in force.

## Yaw ablation outcome — D-86 (2026-09-11)

One opt-in Gemma yaw trial failed: false stop 25.20 m from target; target never
visible in replay; closest 24.74 m. Default profile unchanged; do not expand.
308 unit/contract tests pass. No cloud quota used, no run remains active.
Read `docs/research/c5_navigation_audit_20260910/YAW_RESULT_20260911.md`.
Next: inspect the saved false-stop frame and target-consistency logic offline.
Do not treat the verified yaw discrepancy as a demonstrated navigation fix.

## Research audit — D-85 (2026-09-10)

Read `docs/research/c5_navigation_audit_20260910/REPORT.md` before another
navigation change. Review retained 24 primary works from 41 candidates.
Verified discrepancy: OnFly goal-facing yaw versus local path-carrot yaw;
causal contribution remains untested. Repaired Gemma still has grounding error.
C1 receives labeled metric detections, preventing an equal-input planning
comparison. Keep the task and frozen substrate. Next: zero-call visibility,
goal and carrot trace before considering an isolated yaw ablation under a new
implementation decision. No new inference or flights during this review.
Quota blocks and held-out restrictions remain in force.

## Free-provider router — D-84 (2026-09-10)

User requested failover among Gemini, Groq, Mistral and OpenRouter. The opt-in
`c5_free_vlm_router_dev` profile is implemented and mock-tested. It stays on the
working provider, switches on 429/network/5xx, persists quota blocks and never
selects paid OpenRouter IDs. Actual provider/model are logged per call.
306 unit/contract tests pass. This is not yet a validated navigation profile.
Gemini, Groq and OpenRouter key-file paths are configured in ignored .env.
User prohibits inspecting key contents; runtime reads them for authentication only.
OpenRouter is pinned to catalog-verified zero-priced google/gemma-4-26b-a4b-it:free.
The single requested simulation made exactly two provider attempts: Gemini 429,
then OpenRouter 429. Both quota markers persisted, no retries or probes, no movement.
See FREE_ROUTER_SCREEN_20260910.json. No experiment is running.
Groq remains disabled pending free-only billing confirmation; Mistral has no key.
Do not restart quota-blocked routes without fresh authorization. Keep Gemma resident.
Guide: docs/FREE_VLM_ROUTER.md. Navigation remains unresolved.

## Active model decision — 2026-09-07 (D-73)

Use `c5_onfly_active_dev` for active C5 navigation development. Both policy
and monitor use `gemma4:e2b`, including the actual inference backend. This is
a working-model selection, not a passed navigation gate. Keep Gemma fixed
while tracing waypoint proposals through verification, replanning, monitor
interventions and actual movement. Do not infer that VLM quality is ruled out.

The user authorizes sharing the resident Gemma model with the valley experiment.
Do not load Qwen or unload Gemma for routine preparation. Shared-server measured
latency may include contention; isolated latency benchmarks require separate
conditions. Historical profiles/results remain frozen; the old Qwen sweep
stays paused. This section supersedes model-selection and GPU-exclusivity
guidance in the earlier handoff below.

## Navigation investigation — D-74–D-82

The same-weight Gemma runtime repair is installed on the shared `gemma4:e2b`
tag. All 1,411 multimodal tensors are byte-verified; original package backup:
`gemma4:e2b-before-projector-fix-20260907`. Audio remains unevaluated.
Details: `reports/paper_implementation/GEMMA_RUNTIME_REPAIR_20260907.md`.

The repaired target-bound profile finished **0/5** development flights:
three timeouts and two false stops. No collisions. Navigation remains unresolved.
See `GEMMA_RUNTIME_FIXED_TARGET_STOP_GATE_20260907.json`. No gate is running.
Historical profiles keep their original digest pins.

User authorized a free-tier Gemini comparison (D-81/D-82). Gemini passed three
matched image grounding checks, but the first C5 flight hit HTTP 429 after 4 s
and six successful calls. See `GEMINI_C5_QUOTA_SCREEN_20260907.json`.
D-83: user requested a fresh attempt on September 10; the old quota marker
was archived. That run stopped on HTTP 503 after 2 simulated seconds, with
no retry or fallback. See `GEMINI_C5_SCREEN_20260910.json`. Both runs are
interrupted and invalid for navigation conclusions. No run is active.
Gemma remains the local default; keep its shared runner available to valley.
295 unit/contract tests and focused Gemini lint checks pass.

Next: continue diagnosing target grounding and waypoint/control flow locally.
Image-level Gemini improvement does not establish solved navigation. D-79/D-80
record unsuccessful prompt and depth-candidate probes; neither is deployed.

## Latest tested state — 2026-09-07 (D-70–D-72)

- Corrected Qwen target-bound arrival profile: **0/5**, all timeouts, no false
  stops/collisions/parse errors; positive control regressed. Not accepted.
- True Gemma 4 E2B baseline profile: **0/5**, all timeouts, no false stops or
  collisions. Actual policy and monitor model IDs were verified in every log.
- Gemma uses ~1.71 GB GPU at context 8192; measured calls ~0.35 s policy,
  ~0.73 s monitor. Lighter/faster does not establish better navigation.
- Qwen fence-only 90 s screen: **1/3 completed**, no recovery triggers.
  Long-horizon boundary and combined-fix gates were paused for the Gemma
  comparison and remain unvalidated. Nothing new is accepted.
- Output budget for the new six-field monitor must exceed the old 48-token
  cap; D-70 uses 96. The first truncated run is invalid, not a capability result.
- 285 unit/contract tests pass after adding a model-ID mismatch guard.
  See `reports/paper_implementation/GEMMA4_E2B_COMPARISON_20260907.md`.

## Model identity correction — 2026-09-07

D-71 supersedes the D-68 model comparison: all five c5_gemma_dir_s1060–1064
runs actually called qwen3-vl:4b for policy and monitor. Do not cite these as
Gemma evidence or proof that defects reproduce across models. User requested
Gemma 4 E2B comparison; new c5_gemma4_e2b_*_dev profiles set the backend too.
Check actual inference_call.model_id, not just policy/config display names.

## Continuation — 2026-09-07

User approved arrival repair first, then boundary recovery, tested separately.
D-69 records the design. Three new `c5_onfly_*_dev` profiles isolate target-bound
arrival, fence recovery, and their combination; frozen profiles are unchanged.
Initial CPU regressions passed; the later real-model results are summarized
above. Do not label the new profiles accepted.
Details and commands: `reports/paper_implementation/C5_ARRIVAL_FENCE_FIXES_20260907.md`.
The earlier geofence diagnosis explains terminal deadlock in long runs, not
necessarily the original 90 s navigation failures. Steering entropy measures
variation, not steering correctness. Target-bound depth does not guarantee
semantic identity; validate false stops in exact replay.

## Earlier handoff — 2026-09-04

The harness works and catches its own defects. **C5 OnFly is the live front**,
and this week's work located its failure precisely.

Current five-seed development result on `grid_nav_onfly_native_long`
(240 s horizon, seeds 1060-1064):

| configuration | success |
| --- | ---: |
| `c0` classical planner, knows the goal | **5/5**, 63-84 s |
| C5 + Qwen3-VL 4B, pixel output | 1/5 |
| C5 + Qwen3-VL 4B, pixel output, told the winning route | 0/5 |
| C5 + Qwen3-VL 4B, five-word steering output, told the route | 0/5 |
| C5 + Gemma 3 4B, five-word steering output | 0/5 |

Five candidate causes have each been separately excluded by measurement:

- **Path budget** — raising the horizon 90 s to 240 s changed no outcome; the
  failures used 78-90 m of a 144 m budget (D-64).
- **Step source** — the vehicle realises under 10% of any commanded step before
  replanning, so waypoint distance barely reaches it (D-62).
- **Search and viewpoint choice** — the target is dead ahead at 35 m on every
  seed; there is nothing to search for (D-64).
- **Not knowing the route** — handed `c0`'s winning path in words, C5 does
  *worse*, 0/5 against 1/5 (D-66).
- **Output representation** — a five-word steering vocabulary scores 0/5 too,
  and the model simply repeats one word instead of one pixel (D-67).

What is left are **two model-independent defects**, both reproduced under two
different VLMs:

1. **Geofence deadlock.** The vehicle reaches ~55 m of the 60 m fence, every
   subsequent proposal lands outside it and is correctly refused, and nothing
   turns it around. It then holds position until the horizon expires. On the
   failing seeds 100% of verifier calls during the freeze are geofence refusals;
   the one success has zero across the whole episode (D-65, D-68).
2. **Acquisition latch false stops.** The monitor declares arrival at 8.5 m,
   14.2 m and 32.9 m from a 2 m goal radius, reporting
   `latest_scale=large, acquisition_count=2/2` — on seed 1060 while the vehicle
   had moved barely 2 m from its start (D-67, D-68).

A third finding is real but **not** currently binding: Qwen3-VL 4B does not
steer. Mean normalised entropy over the five-word vocabulary is 0.21 against
Gemma's 0.60, with no overlap between the two sets, and Qwen never selected
`hard_left` or `hard_right` in 925 decisions. Gemma steers three times better
and still scores 0/5, so fixing steering alone would not have changed a single
outcome (D-68).

## What to do next, in order

1. **Fix the geofence deadlock.** It blocks four of five seeds under both
   models. The fix is a fallback when every proposal is refused for the fence —
   an architecture decision, so record it as a `D-nn` before implementing.
   Success criterion: no episode ends frozen with 100% geofence refusals.
2. **Fix the acquisition latch.** Four false stops so far. A stop declared at
   32.9 m with `latest_scale=large` means the scale evidence is not constraining
   anything. Success criterion: no `agent_stopped` outside the goal radius.
3. **Re-run the five-seed gate** on `grid_nav_onfly_native_dynamics` (the frozen
   90 s profile) after 1 and 2, and compare against
   `reports/paper_implementation/C5_RETAINED_FIVE_SEED_RESULTS_20260901.md`.
4. **Only then** revisit steering and model choice.

Everything else open is in [`TODO.md`](TODO.md), ordered by what it blocks.

## Rules that must not be broken

- **Held-out seeds 1-40 are never trained on and never tuned against.**
  Development uses 1060-1064; training collection uses 1000+. This is enforced
  in `src/uavlab/training/splits.py` — do not work around it.
- **Do not hide the remaining search boundary** with colour detection,
  simulator truth, scripted target search, or a weaker SUPER substrate. This is
  the standing instruction that makes the negative results meaningful.
- **Privileged diagnostics are never reportable.** Configs tagged
  `privileged_diagnostic` (`c5_route_hint_s*`, `c5_route_direction_s*`) feed the
  model a route derived from `c0`'s successful trajectory, i.e. simulator truth.
  They answer "can the agent execute a route it is told?" and nothing else.
  Their numbers must not appear in any results table.
- **One seed is not a result.** Three readings this week were reversed by later
  seeds, and in each case the misleading seed was the one that ended early with
  few decisions. Check the sample size before concluding.
- **Verify a contract experiment distributionally.** The direction contract's
  original acceptance criterion asked whether bearings spread beyond +-10
  degrees, which a model emitting one fixed word passes. Use entropy or modal
  share (D-67).

## Running things

```bash
export PYTHONPATH=src
python -m uavlab.cli run --arch c5_onfly_active_dev \
  --env grid_nav_onfly_native_long --seed 1060 --out runs/probe
python -m uavlab.cli verify c5          # does the architecture function
python -m pytest tests -q               # full suite, ~10 min
```

Two tests are sensitive to machine load rather than broken —
`tests/integration/test_verify.py::[c1]` (drives real `gpt-oss:20b`) and
`tests/smoke/test_all_architectures.py::test_the_core_runtime_imports_no_heavy_dependency`.
Both pass in isolation; run the suite on an idle machine before believing a red
result (D-63).

For resource diagnostics, inspect GPU usage. D-73 permits the valley experiment
to share the same resident Gemma model; GPU exclusivity is not a prerequisite:

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

## Commit state

As of D-93, all implementation/configuration changes and session outcomes are
committed. Historical scratch scripts/logs remain untracked; credentials are
ignored and were not staged. See CHANGES.md and git log for rollback points.
