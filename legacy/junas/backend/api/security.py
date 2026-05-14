from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic

from fastapi import HTTPException, Request

from api.config import Settings


def _path_is_exempt(path: str) -> bool:
    return path in {
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }


def authorize_request(request: Request, settings: Settings) -> str | None:
    if not settings.require_auth:
        return None

    path = request.url.path
    if _path_is_exempt(path):
        return None

    if not path.startswith("/api/v1"):
        return None

    api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key or api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


@dataclass
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class SimpleRateLimiter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._events: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _client_id(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = request.client
        if client is not None and client.host:
            return client.host
        return "unknown"

    def _limit_for_path(self, path: str) -> int:
        if path.startswith("/api/v1/research/ask"):
            return max(1, int(self.settings.rate_limit_research_per_minute))
        if path.startswith("/api/v1/search"):
            return max(1, int(self.settings.rate_limit_search_per_minute))
        return max(1, int(self.settings.rate_limit_default_per_minute))

    def check(self, request: Request) -> RateLimitDecision:
        if not self.settings.rate_limit_enabled:
            return RateLimitDecision(allowed=True, limit=0, remaining=0, retry_after=0)

        path = request.url.path
        if _path_is_exempt(path) or not path.startswith("/api/v1"):
            return RateLimitDecision(allowed=True, limit=0, remaining=0, retry_after=0)

        limit = self._limit_for_path(path)
        now = monotonic()
        window_seconds = 60.0

        bucket_key = f"{self._client_id(request)}:{path}"
        bucket = self._events[bucket_key]

        while bucket and (now - bucket[0]) > window_seconds:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = int(max(1, window_seconds - (now - bucket[0])))
            return RateLimitDecision(
                allowed=False,
                limit=limit,
                remaining=0,
                retry_after=retry_after,
            )

        bucket.append(now)
        remaining = max(0, limit - len(bucket))
        return RateLimitDecision(
            allowed=True,
            limit=limit,
            remaining=remaining,
            retry_after=0,
        )
