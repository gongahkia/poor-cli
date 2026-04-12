"""Token-bucket rate limiting for inbound JSON-RPC methods."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import time
from typing import Any, Callable, Dict, Mapping, Optional


DEFAULT_RPC_RATE_LIMITS: Dict[str, Dict[str, float]] = {
    "default": {"rate": 50, "burst": 100},
    "chatStreaming": {"rate": 2, "burst": 4},
    "poor-cli/chatStreaming": {"rate": 2, "burst": 4},
    "completions/*": {"rate": 10, "burst": 20},
    "poor-cli/completions/*": {"rate": 10, "burst": 20},
    "poor-cli/inlineComplete": {"rate": 10, "burst": 20},
    "poor-cli/getCompletion": {"rate": 10, "burst": 20},
}


@dataclass(frozen=True)
class BucketSpec:
    rate: float
    burst: float


class RateLimitExceeded(Exception):
    def __init__(self, method: str, retry_after_s: float):
        self.method = method
        self.retry_after_s = retry_after_s
        super().__init__(f"rate limited: {method}")


class Bucket:
    def __init__(
        self,
        *,
        rate: float,
        burst: float,
        now: Callable[[], float] = time.monotonic,
        tokens: Optional[float] = None,
        last_refill: Optional[float] = None,
    ):
        if rate <= 0:
            raise ValueError("rate must be positive")
        if burst <= 0:
            raise ValueError("burst must be positive")
        self.refill_rate = float(rate)
        self.capacity = float(burst)
        self._now = now
        self.tokens = min(float(tokens if tokens is not None else burst), self.capacity)
        self.last_refill = float(last_refill if last_refill is not None else now())

    def configure(self, *, rate: float, burst: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if burst <= 0:
            raise ValueError("burst must be positive")
        self.refill()
        self.refill_rate = float(rate)
        self.capacity = float(burst)
        self.tokens = min(self.tokens, self.capacity)

    def refill(self) -> None:
        now = self._now()
        elapsed = max(0.0, now - self.last_refill)
        if elapsed:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    def take(self, amount: float = 1.0) -> bool:
        self.refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def retry_after_s(self, amount: float = 1.0) -> float:
        self.refill()
        missing = max(0.0, amount - self.tokens)
        return missing / self.refill_rate


class RateLimiter:
    def __init__(
        self,
        policy: Optional[Mapping[str, Mapping[str, Any]]] = None,
        *,
        now: Callable[[], float] = time.monotonic,
    ):
        self._now = now
        self._policy: Dict[str, BucketSpec] = {}
        self._buckets: Dict[str, Bucket] = {}
        self.disabled = False
        self.configure(policy if policy is not None else DEFAULT_RPC_RATE_LIMITS)

    def configure(self, policy: Optional[Mapping[str, Mapping[str, Any]]]) -> None:
        if policy == {}:
            self.disabled = True
            self._policy = {}
            self._buckets = {}
            return
        self.disabled = False
        parsed = self._parse_policy(policy if policy is not None else DEFAULT_RPC_RATE_LIMITS)
        next_buckets: Dict[str, Bucket] = {}
        for key, spec in parsed.items():
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = Bucket(rate=spec.rate, burst=spec.burst, now=self._now)
            else:
                bucket.configure(rate=spec.rate, burst=spec.burst)
            next_buckets[key] = bucket
        self._policy = parsed
        self._buckets = next_buckets

    def take(self, method: str) -> bool:
        allowed, _ = self.check(method)
        return allowed

    def check(self, method: str) -> tuple[bool, float]:
        if self.disabled:
            return True, 0.0
        key = self._match_key(method)
        bucket = self._buckets[key]
        if bucket.take():
            return True, 0.0
        return False, bucket.retry_after_s()

    def require(self, method: str) -> None:
        allowed, retry_after_s = self.check(method)
        if not allowed:
            raise RateLimitExceeded(method, retry_after_s)

    def _match_key(self, method: str) -> str:
        aliases = self._method_aliases(method)
        for alias in aliases:
            if alias in self._policy and alias != "default":
                return alias
        for key in self._policy:
            if key == "default":
                continue
            for alias in aliases:
                if fnmatchcase(alias, key):
                    return key
        return "default"

    @staticmethod
    def _method_aliases(method: str) -> list[str]:
        aliases = [method]
        if method.startswith("poor-cli/"):
            aliases.append(method[len("poor-cli/"):])
        if "/" in method:
            aliases.append(method.rsplit("/", 1)[-1])
        return list(dict.fromkeys(aliases))

    @staticmethod
    def _parse_policy(policy: Mapping[str, Mapping[str, Any]]) -> Dict[str, BucketSpec]:
        parsed: Dict[str, BucketSpec] = {}
        for key, raw_spec in policy.items():
            if not isinstance(raw_spec, Mapping):
                raise ValueError(f"rate limit for {key} must be a mapping")
            if "rate" not in raw_spec or "burst" not in raw_spec:
                raise ValueError(f"rate limit for {key} must include rate and burst")
            rate = float(raw_spec["rate"])
            burst = float(raw_spec["burst"])
            if rate <= 0 or burst <= 0:
                raise ValueError(f"rate limit for {key} must be positive")
            parsed[str(key)] = BucketSpec(rate=rate, burst=burst)
        if "default" not in parsed:
            parsed["default"] = BucketSpec(
                rate=float(DEFAULT_RPC_RATE_LIMITS["default"]["rate"]),
                burst=float(DEFAULT_RPC_RATE_LIMITS["default"]["burst"]),
            )
        return parsed
