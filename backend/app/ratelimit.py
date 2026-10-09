import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from .config import settings
from .models import User
from .security import get_current_user


class SlidingWindowLimiter:
    """rules: [(max_requests, window_seconds, label)]. Counts per key (user id)."""

    def __init__(self, rules: list[tuple[int, int, str]]):
        self.rules = rules
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()  # sync endpoints run in a thread pool

    def check(self, key: int) -> tuple[int, str] | None:
        """Returns None if allowed (and records the hit), else (retry_after_seconds, label)."""
        now = time.monotonic()
        longest = max(window for _, window, _ in self.rules)
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > longest:
                hits.popleft()
            for limit, window, label in self.rules:
                recent = [t for t in hits if now - t <= window]
                if len(recent) >= limit:
                    return int(window - (now - recent[0])) + 1, label
            hits.append(now)
        return None


def limit_per_user(limiter: SlidingWindowLimiter):
    """FastAPI dependency: authenticates, then enforces the limiter."""
    def dependency(user: User = Depends(get_current_user)) -> User:
        blocked = limiter.check(user.id)
        if blocked:
            retry, label = blocked
            wait = f"{retry // 60} min" if retry >= 120 else f"{retry} s"
            raise HTTPException(
                429,
                f"Rate limit reached ({label}). Try again in about {wait}.",
                headers={"Retry-After": str(retry)},
            )
        return user
    return dependency


ask_limit = limit_per_user(SlidingWindowLimiter([
    (settings.ask_per_minute, 60, f"{settings.ask_per_minute} questions per minute"),
    (settings.ask_per_day, 86400, f"{settings.ask_per_day} questions per day"),
]))

index_limit = limit_per_user(SlidingWindowLimiter([
    (settings.index_per_hour, 3600, f"{settings.index_per_hour} index builds per hour"),
]))