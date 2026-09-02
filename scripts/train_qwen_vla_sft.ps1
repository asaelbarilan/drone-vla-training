param(
    [string]$DataDir = "data/qwen_vla_sft",
    [string]$OutputDir = "models/qwen3_vl_4b_vla_lora",
    [string]$Model = "Qwen/Qwen3-VL-4B-Instruct"
)

$ErrorActionPreference = "Stop"
$env:IMAGE_MAX_TOKEN_NUM = "64"
$env:PYTORCH_CUDA_ALLOC_CONF = "expandable_segments:True"

& uavlab validate-qwen-vla --data $DataDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Get-Command swift -ErrorAction SilentlyContinue)) {
    throw "ms-swift is not installed. Install ms-swift>=4.0 and bitsandbytes in a training environment."
}

$swiftArgs = @(
    "sft",
    "--model", $Model,
    "--dataset", (Join-Path $DataDir "train_swift.jsonl"),
    "--val_dataset", (Join-Path $DataDir "val_swift.jsonl"),
    "--tuner_type", "lora",
    "--quant_method", "bnb",
    "--quant_bits", "4",
    "--bnb_4bit_compute_dtype", "bfloat16",
    "--bnb_4bit_quant_type", "nf4",
    "--bnb_4bit_use_double_quant", "true",
    "--torch_dtype", "bfloat16",
    "--num_train_epochs", "3",
    "--per_device_train_batch_size", "1",
    "--per_device_eval_batch_size", "1",
    "--gradient_accumulation_steps", "16",
    "--learning_rate", "1e-4",
    "--lora_rank", "8",
    "--lora_alpha", "32",
    "--target_modules", "all-linear",
    "--freeze_vit", "true",
    "--freeze_aligner", "true",
    "--gradient_checkpointing", "true",
    "--max_length", "512",
    "--eval_steps", "100",
    "--save_steps", "100",
    "--save_total_limit", "2",
    "--logging_steps", "5",
    "--warmup_ratio", "0.05",
    "--dataset_num_proc", "2",
    "--dataloader_num_workers", "2",
    "--output_dir", $OutputDir
)

& swift @swiftArgs
exit $LASTEXITCODE
