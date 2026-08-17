# Production LLM Gateway

A production-minded FastAPI policy edge in front of the LiteLLM Proxy. Client
applications receive one OpenAI-compatible interface while provider credentials,
model selection, fallbacks, caching, usage accounting, and spend controls remain
centralized.

## Why this exists

Calling an LLM SDK directly from every application creates duplicated retry
logic, scattered credentials, inconsistent logging, and provider lock-in. This
project separates those responsibilities:

```text
Applications and agents
        │ X-API-Key + logical model alias
        ▼
FastAPI policy edge :8000
  authentication · rate limits · request bounds · signed webhooks
        │ scoped LiteLLM virtual key
        ▼
LiteLLM Proxy :4000
  routing · fallbacks · cache · usage/cost ledger · provider credentials
        ├── OpenAI
        ├── Groq
        └── local Ollama
```

Applications request a policy alias—`fast`, `balanced`, `reasoning`, or
`private`—rather than a provider model ID. The edge rejects direct model names,
which prevents clients from bypassing reviewed routing and data-handling policy.

## Implemented capabilities

- OpenAI-compatible `POST /v1/chat/completions` and `POST /v1/responses`
- Server-sent event streaming for both endpoints
- Backward-compatible `POST /v1/generate` with signed HTTPS webhooks
- Wrapper API-key authentication and Redis-backed distributed per-client rate limiting
- Pre-provider email, payment-card-like, and Canadian SIN-like data redaction
- Alias-only model policy and configurable input/output limits
- Request IDs, metadata-only access logs, normalized errors, timeouts, and
  retries limited to transient upstream failures
- LiteLLM multi-deployment routing, fallbacks, Redis caching, PostgreSQL usage
  records, virtual keys, and budget controls
- Health/readiness probes, Pydantic validation, tests, and a non-root image

## Quick start

Copy the example configuration and replace every placeholder:

```bash
cp .env.example .env
docker compose up --build
```

Create a scoped LiteLLM virtual key for the edge service instead of placing the
LiteLLM master key in `LLM_GATEWAY_API_KEY`. Provider keys belong only in the
LiteLLM container or a secret manager; gateway clients never receive them.

The API documentation is available at `http://localhost:8000/docs`.

### Chat Completions

```bash
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: local-development-key' \
  -d '{
    "model": "fast",
    "messages": [{"role": "user", "content": "Explain idempotency briefly."}]
  }'
```

### Responses

```bash
curl http://localhost:8000/v1/responses \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: local-development-key' \
  -d '{"model":"reasoning","input":"Design a retry policy for a payment API."}'
```

Set `"stream": true` on either contract to receive the upstream event stream.

## Routing policy

The checked-in LiteLLM example defines:

| Alias | Intended workload | Example deployments |
|---|---|---|
| `fast` | Low-latency, high-volume work | efficient OpenAI model plus Groq fallback pool |
| `balanced` | General application work | balanced OpenAI deployment |
| `reasoning` | Difficult analysis and tool workflows | capability-first OpenAI deployment |
| `private` | Data that must remain local | Ollama deployment |

Treat these as deployment policy, not permanent model choices. Change provider
models in `config/litellm.yaml` without changing application code. Evaluate
fallback models on the same golden test set before treating them as equivalent.

## Security and privacy boundaries

- Do not log raw prompts or responses by default. The sample disables LiteLLM
  message logging while retaining operational and spend metadata.
- Never commit `.env`, provider keys, LiteLLM master keys, virtual keys, database
  passwords, or customer prompts.
- Use tenant-scoped virtual keys with budgets and expiration—not one shared key.
- Cache only workloads whose data policy permits it. Include tenant and policy
  boundaries in any custom cache key strategy.
- Put TLS, network policy, egress allowlists, secret management, and Redis/Postgres
  authentication around the sample Compose topology before deployment.
- Keep provider fallbacks within approved data residency and retention boundaries.

## Local development and verification

The unit suite does not call a paid model:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
ruff check .
```

The tests verify authentication, rate limiting, alias enforcement, request
bounds, normalized provider failures, and webhook safety. Run a separate opt-in
integration test against a development LiteLLM virtual key before deployment.

## Production follow-ups

Add a durable webhook outbox for guaranteed delivery,
an authenticated metrics endpoint, distributed traces, per-tenant cache policy,
and deployment-specific guardrails. Pin the LiteLLM container by immutable digest
after validation rather than following a floating tag.
