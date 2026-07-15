"""Thread-safe token-bucket rate limiter (DEL-01).

The hourly delivery run posts to Telegram from several worker threads at once.
Telegram enforces a global ceiling (~30 messages/second to distinct chats), so a
single process-wide limiter — acquired before every send — keeps the aggregate
rate under the ceiling regardless of how many workers are running.
"""
import threading
import time


class TokenBucket:
    """A classic token bucket.

    Tokens refill continuously at ``rate_per_sec`` up to ``burst`` capacity.
    ``acquire`` blocks until a token is available. Safe to share across threads.
    """

    def __init__(self, rate_per_sec: float, burst: float | None = None):
        self.rate = max(0.001, float(rate_per_sec))
        self.capacity = float(burst) if burst is not None else max(1.0, self.rate)
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._cond = threading.Condition(threading.Lock())

    def _refill_locked(self, now: float) -> None:
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last = now

    def acquire(self, n: int = 1) -> None:
        """Block until ``n`` tokens are available, then consume them."""
        with self._cond:
            while True:
                now = time.monotonic()
                self._refill_locked(now)
                if self._tokens >= n:
                    self._tokens -= n
                    return
                # Not enough yet — wait just long enough for the deficit to refill.
                deficit = n - self._tokens
                self._cond.wait(timeout=deficit / self.rate)

    def available(self) -> float:
        """Current token count (mainly for tests/introspection)."""
        with self._cond:
            self._refill_locked(time.monotonic())
            return self._tokens
