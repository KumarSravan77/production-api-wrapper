import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import Settings, get_settings
from app.models import ChatCompletionRequest, GenerateRequest, ResponsesRequest
from app.provider import GatewayProvider, ProviderError
from app.rate_limit import InMemoryRateLimiter
from app.webhooks import deliver_webhook, validate_webhook_url

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("api-wrapper")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.http = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    app.state.provider = GatewayProvider(
        app.state.http,
        settings.gateway_api_key,
        settings.gateway_base_url,
        settings.max_retries,
    )
    app.state.limiter = InMemoryRateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_seconds
    )
    yield
    await app.state.http.aclose()


app = FastAPI(title="Production LLM Gateway", version="0.2.0", lifespan=lifespan)


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
    configured = bool(settings.gateway_api_key and settings.allowed_model_aliases)
    return JSONResponse(
        status_code=200 if configured else 503,
        content={
            "status": "ready" if configured else "not_ready",
            "gateway_configured": configured,
            "model_aliases": sorted(settings.allowed_model_aliases),
        },
    )


def apply_policy(body: Dict[str, Any], settings: Settings) -> Dict[str, Any]:
    body["model"] = body.get("model") or settings.default_model_alias
    if body["model"] not in settings.allowed_model_aliases:
        raise HTTPException(422, "Requested model alias is not allowed")
    output_limit = body.get("max_output_tokens") or body.get("max_completion_tokens") or body.get(
        "max_tokens"
    )
    if output_limit and output_limit > settings.max_output_tokens:
        raise HTTPException(422, f"Output is capped at {settings.max_output_tokens} tokens")
    input_size = len(json.dumps(body.get("input", body.get("messages", [])), default=str))
    if input_size > settings.max_input_characters:
        raise HTTPException(413, "Input exceeds the gateway size limit")
    return body


def rate_limit_headers(request: Request, settings: Settings) -> Dict[str, str]:
    remaining, reset = request.state.rate_limit
    return {
        "X-RateLimit-Limit": str(settings.rate_limit_requests),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset),
        "X-Model-Policy": "alias-only",
    }


@app.post("/v1/chat/completions", tags=["gateway"])
async def chat_completions(
    payload: ChatCompletionRequest,
    request: Request,
    _identity: str = Depends(authorize),
    settings: Settings = Depends(get_settings),
):
    body = apply_policy(payload.model_dump(exclude_none=True), settings)
    if payload.stream:
        return StreamingResponse(
            request.app.state.provider.stream("chat/completions", body, request.state.request_id),
            media_type="text/event-stream",
            headers=rate_limit_headers(request, settings),
        )
    result = await request.app.state.provider.create_chat_completion(
        body, request.state.request_id
    )
    return JSONResponse(content=result, headers=rate_limit_headers(request, settings))


@app.post("/v1/responses", tags=["gateway"])
async def responses(
    payload: ResponsesRequest,
    request: Request,
    _identity: str = Depends(authorize),
    settings: Settings = Depends(get_settings),
):
    body = apply_policy(payload.model_dump(exclude_none=True), settings)
    if payload.stream:
        return StreamingResponse(
            request.app.state.provider.stream("responses", body, request.state.request_id),
            media_type="text/event-stream",
            headers=rate_limit_headers(request, settings),
        )
    result = await request.app.state.provider.create_response(body, request.state.request_id)
    return JSONResponse(content=result, headers=rate_limit_headers(request, settings))


@app.post("/v1/generate", tags=["generation"])
async def generate(
    payload: GenerateRequest, request: Request, tasks: BackgroundTasks,
    _identity: str = Depends(authorize), settings: Settings = Depends(get_settings),
):
    body = payload.model_dump(exclude_none=True, exclude={"webhook"})
    body = apply_policy(body, settings)
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
        tasks.add_task(
            deliver_webhook,
            request.app.state.http,
            url,
            event,
            settings.webhook_signing_secret,
        )
    return JSONResponse(content=result, headers=rate_limit_headers(request, settings))
