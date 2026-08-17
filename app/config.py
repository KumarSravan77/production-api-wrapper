import os
from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet


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
    gateway_api_key: str
    default_model_alias: str
    gateway_base_url: str
    allowed_model_aliases: FrozenSet[str]
    wrapper_api_keys: FrozenSet[str]
    rate_limit_requests: int
    rate_limit_window_seconds: int
    redis_url: str
    request_timeout_seconds: float
    max_retries: int
    webhook_signing_secret: str
    webhook_allow_http: bool
    max_input_characters: int
    max_output_tokens: int


@lru_cache
def get_settings() -> Settings:
    keys = frozenset(x.strip() for x in os.getenv("WRAPPER_API_KEYS", "").split(",") if x.strip())
    aliases = frozenset(
        x.strip()
        for x in os.getenv("ALLOWED_MODEL_ALIASES", "fast,balanced,reasoning,private").split(",")
        if x.strip()
    )
    default_alias = os.getenv("DEFAULT_MODEL_ALIAS", "balanced")
    if default_alias not in aliases:
        raise RuntimeError("DEFAULT_MODEL_ALIAS must be in ALLOWED_MODEL_ALIASES")
    return Settings(
        gateway_api_key=os.getenv("LLM_GATEWAY_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        default_model_alias=default_alias,
        gateway_base_url=os.getenv(
            "LLM_GATEWAY_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/"),
        allowed_model_aliases=aliases,
        wrapper_api_keys=keys,
        rate_limit_requests=integer("RATE_LIMIT_REQUESTS", 60, 1),
        rate_limit_window_seconds=integer("RATE_LIMIT_WINDOW_SECONDS", 60, 1),
        redis_url=os.getenv("REDIS_URL", ""),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
        max_retries=integer("MAX_RETRIES", 2),
        webhook_signing_secret=os.getenv("WEBHOOK_SIGNING_SECRET", ""),
        webhook_allow_http=os.getenv("WEBHOOK_ALLOW_HTTP", "false").lower() == "true",
        max_input_characters=integer("MAX_INPUT_CHARACTERS", 100000, 1),
        max_output_tokens=integer("MAX_OUTPUT_TOKENS", 8192, 1),
    )
