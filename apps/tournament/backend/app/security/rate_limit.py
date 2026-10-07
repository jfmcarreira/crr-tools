from threading import RLock

from .session import timestamp_ms


class LoginRateLimiter:
    def __init__(self, maximum_failures: int = 5, window_ms: int = 15 * 60 * 1000):
        self.maximum_failures = maximum_failures
        self.window_ms = window_ms
        self.attempts: dict[str, tuple[int, int]] = {}
        self.lock = RLock()

    def limited(self, key: str, now: int | None = None) -> bool:
        now = timestamp_ms() if now is None else now
        with self.lock:
            for expired in [key for key, (_, reset) in self.attempts.items() if reset <= now]:
                del self.attempts[expired]
            return self.attempts.get(key, (0, 0))[0] >= self.maximum_failures

    def failure(self, key: str, now: int | None = None) -> None:
        now = timestamp_ms() if now is None else now
        with self.lock:
            count, reset = self.attempts.get(key, (0, now + self.window_ms))
            if reset <= now:
                count, reset = 0, now + self.window_ms
            self.attempts[key] = (count + 1, reset)

    def clear(self, key: str) -> None:
        with self.lock:
            self.attempts.pop(key, None)
