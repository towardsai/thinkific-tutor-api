from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimit:
    name: str
    max_requests: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit_name: str = ""
    retry_after_seconds: int = 0
    remaining: int = 0


class FixedWindowRateLimiter:
    def __init__(self, limits: tuple[RateLimit, ...]) -> None:
        self._limits = tuple(limit for limit in limits if limit.max_requests > 0)
        self._state: dict[tuple[str, str], tuple[int, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> RateLimitResult:
        now = int(time.time())
        with self._lock:
            self._prune(now)
            for limit in self._limits:
                state_key = (key, limit.name)
                window_start, count = self._state.get(
                    state_key, (self._window_start(now, limit.window_seconds), 0)
                )
                if now - window_start >= limit.window_seconds:
                    window_start = self._window_start(now, limit.window_seconds)
                    count = 0
                if count >= limit.max_requests:
                    retry_after = max(1, limit.window_seconds - (now - window_start))
                    return RateLimitResult(
                        allowed=False,
                        limit_name=limit.name,
                        retry_after_seconds=retry_after,
                        remaining=0,
                    )

            remaining = 0
            for limit in self._limits:
                state_key = (key, limit.name)
                window_start, count = self._state.get(
                    state_key, (self._window_start(now, limit.window_seconds), 0)
                )
                if now - window_start >= limit.window_seconds:
                    window_start = self._window_start(now, limit.window_seconds)
                    count = 0
                count += 1
                self._state[state_key] = (window_start, count)
                remaining = (
                    limit.max_requests - count
                    if not remaining
                    else min(remaining, limit.max_requests - count)
                )
            return RateLimitResult(allowed=True, remaining=max(0, remaining))

    @staticmethod
    def _window_start(now: int, window_seconds: int) -> int:
        return now - (now % window_seconds)

    def _prune(self, now: int) -> None:
        for state_key, (window_start, _count) in list(self._state.items()):
            limit_name = state_key[1]
            limit = next((item for item in self._limits if item.name == limit_name), None)
            if limit is None or now - window_start >= limit.window_seconds * 2:
                del self._state[state_key]
