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
