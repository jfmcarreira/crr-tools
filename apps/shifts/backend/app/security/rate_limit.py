from __future__ import annotations

import time
from threading import RLock


class LoginRateLimiter:
    """Counts failed logins per IP+username within a sliding window.

    Process-local: the counters live in this worker only, so running more than
    one worker multiplies the allowed attempts. Keying on the client address
    relies on the proxy configuration being correct, or everyone behind the
    same proxy shares one bucket.
    """

    def __init__(self, maximum_failures: int = 5, window_seconds: int = 15 * 60):
        self.maximum_failures = maximum_failures
        self.window_seconds = window_seconds
        self.attempts: dict[str, tuple[int, int]] = {}
        self.lock = RLock()

    @staticmethod
    def _now() -> int:
        return int(time.time() * 1000)

    def limited(self, key: str, now: int | None = None) -> bool:
        now = self._now() if now is None else now
        with self.lock:
            for expired in [k for k, (_, reset) in self.attempts.items() if reset <= now]:
                del self.attempts[expired]
            return self.attempts.get(key, (0, 0))[0] >= self.maximum_failures

    def failure(self, key: str, now: int | None = None) -> None:
        now = self._now() if now is None else now
        with self.lock:
            count, reset = self.attempts.get(key, (0, now + self.window_seconds * 1000))
            if reset <= now:
                count, reset = 0, now + self.window_seconds * 1000
            self.attempts[key] = (count + 1, reset)

    def clear(self, key: str) -> None:
        with self.lock:
            self.attempts.pop(key, None)

    def consume(self, key: str) -> bool:
        """Atomically count an attempt, returning False when the bucket is full."""
        with self.lock:
            now = self._now()
            if self.limited(key, now):
                return False
            self.failure(key, now)
            return True
