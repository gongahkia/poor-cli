"""Per-user rate limiting with token bucket algorithm."""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)

DEFAULT_USER_RATE = 10 # messages per minute
DEFAULT_GLOBAL_RATE = 100 # messages per minute


@dataclass
class TokenBucket:
    capacity: float
    rate: float # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.tokens = self.capacity

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def consume(self, n: float = 1.0) -> bool:
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def wait_time(self) -> float:
        self._refill()
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / self.rate


class RateLimiter:
    """per-user and global rate limiter using token bucket."""

    def __init__(self, user_rate: int = DEFAULT_USER_RATE,
                 global_rate: int = DEFAULT_GLOBAL_RATE):
        self._user_rate = user_rate
        self._global_rate = global_rate
        self._user_buckets: Dict[int, TokenBucket] = {}
        self._global_bucket = TokenBucket(
            capacity=float(global_rate),
            rate=global_rate / 60.0,
        )

    def _get_user_bucket(self, user_id: int) -> TokenBucket:
        if user_id not in self._user_buckets:
            self._user_buckets[user_id] = TokenBucket(
                capacity=float(self._user_rate),
                rate=self._user_rate / 60.0,
            )
        return self._user_buckets[user_id]

    def check_rate(self, user_id: int) -> bool:
        """returns True if request is allowed."""
        user_ok = self._get_user_bucket(user_id).consume()
        global_ok = self._global_bucket.consume()
        if not user_ok or not global_ok:
            if not user_ok:
                self._global_bucket.tokens += 1.0 # refund global token
            return False
        return True

    def get_wait_time(self, user_id: int) -> float:
        """seconds until next request allowed."""
        user_wait = self._get_user_bucket(user_id).wait_time()
        global_wait = self._global_bucket.wait_time()
        return max(user_wait, global_wait)

    def get_status(self, user_id: int) -> Dict[str, float]:
        ub = self._get_user_bucket(user_id)
        ub._refill()
        self._global_bucket._refill()
        return {
            "user_tokens": ub.tokens,
            "user_capacity": ub.capacity,
            "global_tokens": self._global_bucket.tokens,
            "global_capacity": self._global_bucket.capacity,
        }

    def cleanup_stale(self, max_age_seconds: float = 600) -> int:
        """remove user buckets not accessed recently."""
        now = time.monotonic()
        stale = [uid for uid, b in self._user_buckets.items() if now - b.last_refill > max_age_seconds]
        for uid in stale:
            del self._user_buckets[uid]
        return len(stale)
