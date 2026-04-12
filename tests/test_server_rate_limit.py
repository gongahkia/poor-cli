import asyncio
import logging

from poor_cli.audit_log import AuditEventType, AuditSeverity
from poor_cli.config import Config, ConfigManager
from poor_cli.server.rate_limit import DEFAULT_RPC_RATE_LIMITS, Bucket, RateLimiter
from poor_cli.server.registry import REGISTRY
from poor_cli.server.runtime import PoorCLIServer
from poor_cli.server.types import JsonRpcMessage, JsonRpcError


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class AuditSink:
    def __init__(self):
        self.events = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)
        return "evt-test"


def test_bucket_refills_over_time():
    clock = Clock()
    bucket = Bucket(rate=1, burst=2, now=clock)

    assert bucket.take() is True
    assert bucket.take() is True
    assert bucket.take() is False

    clock.advance(1)
    assert bucket.take() is True


def test_take_returns_false_when_bucket_exhausted():
    limiter = RateLimiter({"default": {"rate": 1, "burst": 1}}, now=Clock())

    assert limiter.take("poor-cli/getStatusView") is True
    assert limiter.take("poor-cli/getStatusView") is False


def test_hot_methods_limited_lower_than_default():
    limiter = RateLimiter(DEFAULT_RPC_RATE_LIMITS, now=Clock())

    assert [limiter.take("poor-cli/chatStreaming") for _ in range(5)] == [
        True,
        True,
        True,
        True,
        False,
    ]
    assert all(limiter.take("poor-cli/getStatusView") for _ in range(10))


def test_glob_patterns_match_method_groups():
    limiter = RateLimiter(
        {
            "default": {"rate": 100, "burst": 100},
            "completions/*": {"rate": 1, "burst": 1},
        },
        now=Clock(),
    )

    assert limiter.take("poor-cli/completions/create") is True
    assert limiter.take("poor-cli/completions/create") is False
    assert limiter.take("poor-cli/getStatusView") is True


def test_empty_config_disables_limiter():
    limiter = RateLimiter({}, now=Clock())

    assert all(limiter.take("poor-cli/chatStreaming") for _ in range(1000))
    assert limiter.disabled is True


def test_config_supports_user_override_and_disable():
    config = Config.from_dict({"rpc_rate_limits": {"default": {"rate": 1, "burst": 2}}})
    assert config.rpc_rate_limits == {"default": {"rate": 1, "burst": 2}}

    manager = ConfigManager()
    manager.config = Config()
    ConfigManager._deep_merge(manager.config, {"rpc_rate_limits": {}})
    assert manager.config.rpc_rate_limits == {}


def test_config_reload_preserves_existing_bucket_tokens():
    limiter = RateLimiter({"default": {"rate": 1, "burst": 2}}, now=Clock())
    assert limiter.take("poor-cli/getStatusView") is True

    limiter.configure({"default": {"rate": 2, "burst": 3}})

    assert limiter.take("poor-cli/getStatusView") is True
    assert limiter.take("poor-cli/getStatusView") is False


def test_dispatch_returns_429_equivalent_and_audits(monkeypatch):
    server = PoorCLIServer.__new__(PoorCLIServer)
    server.logger = logging.getLogger("test.server.rate_limit")
    server.session_id = "server-test"
    policy = {
        "default": {"rate": 100, "burst": 100},
        "poor-cli/chatStreaming": {"rate": 1, "burst": 1},
    }
    server._rate_limiter = RateLimiter(policy, now=Clock())
    server._rate_limit_policy = policy
    audit = AuditSink()

    async def fake_handler(ctx, params):
        return {"ok": True}

    monkeypatch.setitem(REGISTRY, "poor-cli/chatStreaming", fake_handler)
    monkeypatch.setattr("poor_cli.server.runtime.get_audit_logger", lambda: audit)

    async def run():
        first = await PoorCLIServer.dispatch(
            server,
            JsonRpcMessage(
                id=1,
                method="poor-cli/chatStreaming",
                params={"clientId": "nvim"},
            ),
        )
        second = await PoorCLIServer.dispatch(
            server,
            JsonRpcMessage(
                id=2,
                method="poor-cli/chatStreaming",
                params={"clientId": "nvim"},
            ),
        )
        return first, second

    first, second = asyncio.run(run())

    assert first.result == {"ok": True}
    assert second.error["code"] == JsonRpcError.RATE_LIMITED
    assert second.error["message"] == "rate limited"
    assert second.error["data"]["method"] == "poor-cli/chatStreaming"
    assert second.error["data"]["retry_after_s"] > 0
    assert len(audit.events) == 1
    event = audit.events[0]
    assert event["event_type"] is AuditEventType.RPC_RATE_LIMIT_EXCEEDED
    assert event["severity"] is AuditSeverity.WARNING
    assert event["success"] is False
    assert event["operation"] == "rpc.rate_limit.exceeded"
    assert event["details"]["method"] == "poor-cli/chatStreaming"
    assert event["details"]["client_id"] == "nvim"
