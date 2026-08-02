import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.models import GenerateRequest
from app.provider import OpenAIProvider, ProviderError
from app.rate_limit import InMemoryRateLimiter
from app.webhooks import deliver_webhook, validate_webhook_url

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("api-wrapper")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.http = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    app.state.provider = OpenAIProvider(
        app.state.http, settings.openai_api_key, settings.openai_base_url, settings.max_retries
    )
    app.state.limiter = InMemoryRateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_seconds
    )
    yield
    await app.state.http.aclose()


app = FastAPI(title="Production API Wrapper", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def context(request: Request, call_next: Any) -> Any:
    request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request.state.request_id, request.method, request.url.path, response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


def failure(request: Request, status: int, code: str, message: str, retryable: bool = False):
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "request_id": request.state.request_id,
        "retryable": retryable,
    }})


@app.exception_handler(ProviderError)
async def provider_failure(request: Request, exc: ProviderError):
    return failure(request, exc.status, exc.code, exc.message, exc.retryable)


@app.exception_handler(HTTPException)
async def http_failure(request: Request, exc: HTTPException):
    codes = {401: "unauthorized", 429: "rate_limit_exceeded"}
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return failure(request, exc.status_code, codes.get(exc.status_code, "request_error"), detail)


async def authorize(request: Request, settings: Settings = Depends(get_settings)) -> str:
    key = request.headers.get("X-API-Key", "")
    if settings.wrapper_api_keys and key not in settings.wrapper_api_keys:
        raise HTTPException(401, "A valid X-API-Key header is required")
    identity = key or (request.client.host if request.client else "anonymous")
    allowed, remaining, reset = await request.app.state.limiter.check(identity)
    request.state.rate_limit = remaining, reset
    if not allowed:
        raise HTTPException(429, f"Rate limit exceeded; retry in {reset} seconds")
    return identity


@app.get("/healthz", tags=["operations"])
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["operations"])
async def ready(settings: Settings = Depends(get_settings)):
    configured = bool(settings.openai_api_key)
    return JSONResponse(
        status_code=200 if configured else 503,
        content={"status": "ready" if configured else "not_ready", "provider_configured": configured},
    )


@app.post("/v1/generate", tags=["generation"])
async def generate(
    payload: GenerateRequest, request: Request, tasks: BackgroundTasks,
    _identity: str = Depends(authorize), settings: Settings = Depends(get_settings),
):
    body = payload.model_dump(exclude_none=True, exclude={"webhook"})
    body["model"] = payload.model or settings.openai_model
    result = await request.app.state.provider.create_response(body, request.state.request_id)
    if payload.webhook:
        url = str(payload.webhook.url)
        try:
            validate_webhook_url(url, settings.webhook_allow_http)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not settings.webhook_signing_secret:
            raise HTTPException(503, "Webhook signing is not configured")
        event = {
            "type": "response.completed", "request_id": request.state.request_id,
            "data": result, "metadata": payload.webhook.metadata,
        }
        tasks.add_task(deliver_webhook, request.app.state.http, url, event, settings.webhook_signing_secret)
    remaining, reset = request.state.rate_limit
    return JSONResponse(content=result, headers={
        "X-RateLimit-Limit": str(settings.rate_limit_requests),
        "X-RateLimit-Remaining": str(remaining), "X-RateLimit-Reset": str(reset),
    })
