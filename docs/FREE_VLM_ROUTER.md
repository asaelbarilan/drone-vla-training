# Free vision provider router

Opt-in development profile: `c5_free_vlm_router_dev` (D-84).
The Gemma default and historical single-model profiles are unchanged.

The router uses Gemini, then Groq, Mistral and OpenRouter, staying with the
first working provider. On HTTP 429, network failure or HTTP 5xx it tries the
next enabled provider once. Failed providers stay disabled for the backend
lifetime. HTTP 429 also writes `.local/<provider>_quota_stop`, which blocks
future runs until the user explicitly authorizes resetting that provider.
Malformed output or configuration errors abort; they do not trigger blind retries.
When every confirmed free provider is unavailable, the episode aborts.

## Configuration

The ignored project `.env` contains path-only placeholders. Set each provider's
`API_KEY_FILE` to a file containing the bare API key. Keep the actual secret
out of tracked files. Set that provider's `FREE_TIER_CONFIRMED=true` only after
confirming the account cannot incur paid usage. This is a user confirmation,
not an API billing check. Missing paths/confirmation disable the provider.

- `GEMINI_*`: existing billing-disabled setup.
- `GROQ_*`: default model `qwen/qwen3.8-27b`.
- `MISTRAL_*`: default model `mistral-small-2506`.
- `OPENROUTER_*`: no default model. Select a currently available vision model
  whose exact ID ends in `:free`. The router additionally sends zero price caps
  and disables OpenRouter's provider fallback. Never use an automatic model
  router for a reproducible experiment.

Set `PYTHONPATH=src`, then inspect configuration without any network calls:

```python
from uavlab.plugins.inference.free_vlm_router import FreeVLMRouter
print(FreeVLMRouter().readiness())
```

After configuring available providers, run one development flight:

```text
python -m uavlab.cli run --arch c5_free_vlm_router_dev --env grid_nav_onfly_native_dynamics --seed 1061 --out runs/CHOOSE_NEW_RUN_NAME
```

## Interpretation and validation

Events contain the actual provider, requested and resolved model, role, tokens,
and end-to-end request time. Failure events record HTTP status without secrets.
Successful call latency includes preceding failed attempts for that request;
failure events also expose each failed attempt separately. Do not sum both as
independent total duration. Simulated policy/monitor time remains fixed at
1.0/1.2 seconds for the existing controlled comparison.

Non-Gemini adapters use JSON mode plus the task schema in the prompt. They
check JSON syntax; the existing policy/monitor validates the task fields.
This differs from Gemini's server-enforced schema, so mixed runs are a separate
architecture condition, not a clean single-model quality comparison.

306 CPU unit/contract tests pass, covering failover, quota persistence,
exhaustion, disabled/paid routes, identity, and all three chat API payloads.
Live non-Gemini API compatibility and navigation are not yet validated.

Provider documentation:
- https://console.groq.com/docs/vision
- https://console.groq.com/docs/rate-limits
- https://docs.mistral.ai/studio/conversations/vision
- https://docs.mistral.ai/admin/billing-usage/usage-limits
- https://openrouter.ai/docs/guides/routing/model-variants/free
