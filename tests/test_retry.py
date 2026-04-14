"""tests for poor-cli.retry module."""

import asyncio
import unittest
from poor_cli.retry import RetryConfig, RetryMetrics, with_retry, _compute_delay


class TestComputeDelay(unittest.TestCase):
    def test_exponential_no_jitter(self):
        cfg = RetryConfig(base_delay=1.0, max_delay=30.0, jitter=False)
        self.assertAlmostEqual(_compute_delay(cfg, 0), 1.0)
        self.assertAlmostEqual(_compute_delay(cfg, 1), 2.0)
        self.assertAlmostEqual(_compute_delay(cfg, 2), 4.0)

    def test_max_delay_cap(self):
        cfg = RetryConfig(base_delay=1.0, max_delay=5.0, jitter=False)
        self.assertAlmostEqual(_compute_delay(cfg, 10), 5.0)

    def test_jitter_within_range(self):
        cfg = RetryConfig(base_delay=2.0, max_delay=60.0, jitter=True)
        for _ in range(50):
            delay = _compute_delay(cfg, 0)
            self.assertGreaterEqual(delay, 1.0) # 2.0 * 0.5
            self.assertLessEqual(delay, 2.0) # 2.0 * 1.0


class TestWithRetry(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_success_first_try(self):
        calls = []
        async def fn():
            calls.append(1)
            return "ok"
        result = self._run(with_retry(fn))
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_then_succeeds(self):
        calls = []
        async def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("transient")
            return "ok"
        result = self._run(with_retry(
            fn,
            config=RetryConfig(max_retries=3, base_delay=0.01, jitter=False),
            retryable=lambda e: isinstance(e, ValueError),
        ))
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)

    def test_exhausted_retries_raises(self):
        async def fn():
            raise ValueError("permanent")
        with self.assertRaises(ValueError):
            self._run(with_retry(
                fn,
                config=RetryConfig(max_retries=2, base_delay=0.01, jitter=False),
                retryable=lambda e: isinstance(e, ValueError),
            ))

    def test_non_retryable_raises_immediately(self):
        calls = []
        async def fn():
            calls.append(1)
            raise TypeError("not retryable")
        with self.assertRaises(TypeError):
            self._run(with_retry(
                fn,
                config=RetryConfig(max_retries=3, base_delay=0.01),
                retryable=lambda e: isinstance(e, ValueError),
            ))
        self.assertEqual(len(calls), 1)

    def test_default_retryable_exceptions(self):
        calls = []
        async def fn():
            calls.append(1)
            if len(calls) < 2:
                raise Exception("generic")
            return "ok"
        result = self._run(with_retry(
            fn,
            config=RetryConfig(max_retries=3, base_delay=0.01, jitter=False),
        ))
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
