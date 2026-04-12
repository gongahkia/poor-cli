"""shared retry utility with exponential backoff and jitter."""

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence, Type
from .exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class RetryConfig:
    """retry behavior settings."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: bool = True
    retryable_exceptions: Sequence[Type[BaseException]] = field(
        default_factory=lambda: (Exception,)
    )


@dataclass
class RetryMetrics:
    """metrics collected during a retry sequence."""
    attempts: int = 0
    total_wait: float = 0.0
    last_error: Optional[BaseException] = None
    succeeded: bool = False


def _compute_delay(config: RetryConfig, attempt: int) -> float:
    delay = min(config.base_delay * (2 ** attempt), config.max_delay)
    if config.jitter:
        delay *= random.uniform(0.5, 1.0) # half-to-full jitter
    return delay


async def with_retry(
    fn: Callable[..., Any],
    config: Optional[RetryConfig] = None,
    retryable: Optional[Callable[[BaseException], bool]] = None,
) -> Any:
    """execute *fn* with retries, exponential backoff, and optional jitter.

    Args:
        fn: async callable to execute.
        config: retry configuration (defaults to RetryConfig()).
        retryable: optional predicate; when provided it overrides
                   config.retryable_exceptions for deciding whether to retry.

    Returns:
        the return value of *fn* on success.

    Raises:
        the last exception if all retries are exhausted.
    """
    cfg = config or RetryConfig()
    metrics = RetryMetrics()

    for attempt in range(cfg.max_retries):
        metrics.attempts = attempt + 1
        try:
            result = await fn()
            metrics.succeeded = True
            return result
        except BaseException as exc:
            metrics.last_error = exc
            should_retry = (
                retryable(exc) if retryable is not None
                else isinstance(exc, tuple(cfg.retryable_exceptions))
            )
            if should_retry and attempt < cfg.max_retries - 1:
                delay = _compute_delay(cfg, attempt)
                metrics.total_wait += delay
                logger.debug(
                    "retry %d/%d after %.2fs (%s)",
                    attempt + 1, cfg.max_retries, delay, exc,
                )
                await asyncio.sleep(delay)
                continue
            raise
