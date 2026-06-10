"""per-provider circuit breaker for resilient API execution."""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from .exceptions import CircuitOpenError, setup_logger  # noqa: F401

logger = setup_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed" # normal operation
    OPEN = "open" # tripped, rejecting calls
    HALF_OPEN = "half_open" # testing recovery


@dataclass
class CircuitBreakerConfig:
    """circuit breaker tuning knobs."""
    enabled: bool = False
    failure_threshold: int = 5 # consecutive failures before opening
    recovery_timeout: float = 60.0 # seconds to wait before half-open
    success_threshold: int = 1 # successes in half-open to close


class CircuitBreaker:
    """state machine tracking consecutive failures per provider."""

    def __init__(self, provider_name: str, config: Optional[CircuitBreakerConfig] = None):
        self.provider_name = provider_name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("circuit half-open for %s", self.provider_name)
        return self._state

    def allow_request(self) -> bool:
        """return True if the circuit permits a request."""
        if not self.config.enabled:
            return True
        s = self.state
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.HALF_OPEN:
            return True
        remaining = self.config.recovery_timeout - (time.monotonic() - self._last_failure_time)
        logger.debug("circuit open for %s (%.0fs remaining)", self.provider_name, max(remaining, 0))
        return False

    def record_success(self) -> None:
        """record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("circuit closed for %s after recovery", self.provider_name)
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        """record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("circuit re-opened for %s", self.provider_name)
        elif self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "circuit opened for %s after %d failures",
                self.provider_name, self._failure_count,
            )

    def reset(self) -> None:
        """manually reset to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
