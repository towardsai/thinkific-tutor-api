from __future__ import annotations

from thinkific_tutor.rate_limiter import FixedWindowRateLimiter, RateLimit


def test_fixed_window_rate_limiter_blocks_after_limit() -> None:
    limiter = FixedWindowRateLimiter((RateLimit("minute", 2, 60),))

    assert limiter.check("student-1").allowed
    assert limiter.check("student-1").allowed
    blocked = limiter.check("student-1")

    assert not blocked.allowed
    assert blocked.limit_name == "minute"
    assert blocked.retry_after_seconds > 0


def test_rate_limiter_keys_are_independent() -> None:
    limiter = FixedWindowRateLimiter((RateLimit("minute", 1, 60),))

    assert limiter.check("student-1").allowed
    assert limiter.check("student-2").allowed
    assert not limiter.check("student-1").allowed
