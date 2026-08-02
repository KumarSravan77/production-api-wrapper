import os
from dataclasses import dataclass
from functools import lru_cache


def integer(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    wrapper_api_keys: frozenset
    rate_limit_requests: int
    rate_limit_window_seconds: int
    request_timeout_seconds: float
    max_retries: int
    webhook_signing_secret: str
    webhook_allow_http: bool


@lru_cache
def get_settings() -> Settings:
    keys = frozenset(x.strip() for x in os.getenv("WRAPPER_API_KEYS", "").split(",") if x.strip())
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        wrapper_api_keys=keys,
        rate_limit_requests=integer("RATE_LIMIT_REQUESTS", 60, 1),
        rate_limit_window_seconds=integer("RATE_LIMIT_WINDOW_SECONDS", 60, 1),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
        max_retries=integer("MAX_RETRIES", 2),
        webhook_signing_secret=os.getenv("WEBHOOK_SIGNING_SECRET", ""),
        webhook_allow_http=os.getenv("WEBHOOK_ALLOW_HTTP", "false").lower() == "true",
    )
