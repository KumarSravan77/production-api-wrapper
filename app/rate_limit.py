import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class Window:
    started_at: float
    count: int


class InMemoryRateLimiter:
    """Single-process fixed-window limiter; use Redis for multiple workers."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit, self.window_seconds = limit, window_seconds
        self.windows: Dict[str, Window] = {}
        self.lock = asyncio.Lock()

    async def check(self, key: str) -> Tuple[bool, int, int]:
        now = time.monotonic()
        async with self.lock:
            window = self.windows.get(key)
            if window is None or now - window.started_at >= self.window_seconds:
                window = self.windows[key] = Window(now, 0)
            allowed = window.count < self.limit
            if allowed:
                window.count += 1
            return allowed, max(0, self.limit - window.count), max(
                1, int(self.window_seconds - (now - window.started_at))
            )


class RedisRateLimiter:
    """Atomic fixed-window limiter shared by every gateway replica."""

    def __init__(self, redis_url: str, limit: int, window_seconds: int) -> None:
        from redis.asyncio import from_url

        self.redis = from_url(redis_url, encoding="utf-8", decode_responses=True)
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self, key: str) -> Tuple[bool, int, int]:
        bucket = int(time.time()) // self.window_seconds
        redis_key = f"gateway:rate:{key}:{bucket}"
        async with self.redis.pipeline(transaction=True) as transaction:
            transaction.incr(redis_key)
            transaction.expire(redis_key, self.window_seconds + 1)
            count, _ = await transaction.execute()
        reset = max(1, self.window_seconds - (int(time.time()) % self.window_seconds))
        return count <= self.limit, max(0, self.limit - count), reset

    async def close(self) -> None:
        await self.redis.aclose()
