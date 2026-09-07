#!/usr/bin/env bash
# C5 model-named-step ablation over the retained development seeds.
#
# Needs the GPU to itself: the profile loads Qwen3-VL 4B for both the policy and
# the monitor, and an RTX 4060 Laptop has 8.2 GB total. Check nothing else holds
# it before starting:
#
#     nvidia-smi --query-compute-apps=pid,used_memory --format=csv
#
# Baseline to compare against is c5_onfly_qwen4_native_dynamics on the same
# seeds: 1/5, seed 1060 at 43.206 m final and 0/89 visible decision frames.
# See reports/paper_implementation/C5_RETAINED_FIVE_SEED_RESULTS_20260901.md.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src

for seed in 1060 1061 1062 1063 1064; do
  echo "=== seed ${seed} start $(date +%H:%M:%S)"
  python -m uavlab.cli run \
    --arch c5_onfly_qwen4_spf_step_dev \
    --env grid_nav_onfly_native_dynamics \
    --seed "${seed}" \
    --out "runs/c5_spf_step_s${seed}"
  python scripts/analyze_onfly_run.py "runs/c5_spf_step_s${seed}" \
    --output "reports/paper_implementation/c5_s${seed}_spf_step_analysis.json"
  echo "=== seed ${seed} done $(date +%H:%M:%S)"
done
echo "ALL DONE"
