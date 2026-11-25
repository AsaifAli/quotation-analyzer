"""Bounded in-process rate limiter for the protected QuoteSense API.

The limiter is deliberately dependency-free so existing deployments continue
working without a new Redis service. In multi-worker or multi-instance
production deployments, enforce the same limits at the trusted ingress too.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class SlidingWindowRateLimiter:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds) for a sliding time window."""
        safe_limit = max(1, int(limit))
        safe_window = max(1, int(window_seconds))
        now = self._clock()
        cutoff = now - safe_window

        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= safe_limit:
                retry_after = max(1, int(events[0] + safe_window - now + 0.999))
                return False, retry_after

            events.append(now)

            # Keep the in-memory state bounded during noisy traffic. Oldest
            # entries are evicted only after their events have been recorded;
            # they may lose a limiter bucket, so ingress limits remain required.
            if len(self._events) > 20_000:
                stale_keys = [
                    event_key
                    for event_key, bucket in self._events.items()
                    if not bucket or bucket[-1] <= cutoff
                ]
                for event_key in stale_keys[:5_000]:
                    self._events.pop(event_key, None)

            return True, 0

    def clear(self) -> None:
        """Clear state; intended for deterministic tests and process shutdown."""
        with self._lock:
            self._events.clear()


rate_limiter = SlidingWindowRateLimiter()
