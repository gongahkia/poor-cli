"""tests for poor_cli.circuit_breaker module."""

import time
import unittest
from unittest.mock import patch
from poor_cli.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitOpenError,
)


class TestCircuitBreaker(unittest.TestCase):
    def _make_cb(self, **kwargs):
        cfg = CircuitBreakerConfig(enabled=True, **kwargs)
        return CircuitBreaker("test-provider", cfg)

    def test_starts_closed(self):
        cb = self._make_cb()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_opens_after_threshold(self):
        cb = self._make_cb(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_stays_closed_below_threshold(self):
        cb = self._make_cb(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_success_resets_failure_count(self):
        cb = self._make_cb(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_half_open_after_recovery_timeout(self):
        cb = self._make_cb(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        self.assertEqual(cb._state, CircuitState.OPEN)
        time.sleep(0.06)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.allow_request())

    def test_half_open_success_closes(self):
        cb = self._make_cb(failure_threshold=1, recovery_timeout=0.01, success_threshold=1)
        cb.record_failure()
        time.sleep(0.02)
        _ = cb.state # trigger transition to half-open
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_half_open_failure_reopens(self):
        cb = self._make_cb(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        _ = cb.state
        cb.record_failure()
        self.assertEqual(cb._state, CircuitState.OPEN)

    def test_reset(self):
        cb = self._make_cb(failure_threshold=1)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        cb.reset()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_disabled_always_allows(self):
        cfg = CircuitBreakerConfig(enabled=False)
        cb = CircuitBreaker("test", cfg)
        for _ in range(100):
            cb.record_failure()
        self.assertTrue(cb.allow_request())

    def test_circuit_open_error(self):
        err = CircuitOpenError("my-provider", 42.5)
        self.assertEqual(err.provider_name, "my-provider")
        self.assertAlmostEqual(err.remaining_seconds, 42.5)
        self.assertIn("my-provider", str(err))


if __name__ == "__main__":
    unittest.main()
