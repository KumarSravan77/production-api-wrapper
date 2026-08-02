# Production API Wrapper

A production-minded FastAPI proxy for the OpenAI Responses API.

## Included

- Wrapper API-key authentication
- Per-client rate limiting and rate-limit headers
- Request IDs, structured logs, normalized errors, timeouts, and bounded retries
- Pydantic validation
- HTTPS webhooks signed with HMAC-SHA256
- Health/readiness probes, tests, OpenAPI docs, and a non-root Docker image

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# Load .env with your preferred environment manager.
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs`, then try:

```bash
curl http://localhost:8000/v1/generate \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: local-development-key' \
  -d '{"input":"Explain idempotency in two sentences."}'
```

An optional `webhook` object accepts an HTTPS `url` and arbitrary `metadata`.
Verify callbacks by computing HMAC-SHA256 over `<timestamp>.<raw body>`; headers
`X-Webhook-Timestamp` and `X-Webhook-Signature` carry those values.

## Production note

Replace the in-memory limiter with Redis before using multiple workers. Add an
egress allowlist and persistent delivery records when guaranteed webhook delivery
or stricter SSRF protection is required.

Run the suite with `pytest`.
