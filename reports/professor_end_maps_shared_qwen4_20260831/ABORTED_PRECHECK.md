# Aborted precheck

This partial sweep used a 128-token shared decode cap. C1 AerialClaw responses
were truncated before the JSON object completed, so the sweep was interrupted
and is not a valid result set. The corrected controlled run uses the same
Qwen3-VL 4B model with a shared 512-token cap for every architecture.
