"""tests for poor_cli.cloud_agent module."""

import asyncio
import unittest
from unittest.mock import patch
from poor_cli.cloud_agent import (
    CloudAgentConfig,
    CloudAgentStatus,
    FlyIoProvider,
    GitHubCodespacesProvider,
    get_cloud_provider,
)


class TestCloudAgentConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = CloudAgentConfig()
        self.assertEqual(cfg.provider, "none")
        self.assertEqual(cfg.api_key, "")
        self.assertEqual(cfg.region, "iad")
        self.assertEqual(cfg.max_runtime, 3600)


class TestGetCloudProvider(unittest.TestCase):
    def test_none_returns_none(self):
        cfg = CloudAgentConfig(provider="none")
        self.assertIsNone(get_cloud_provider(cfg))

    def test_fly_io_returns_provider(self):
        cfg = CloudAgentConfig(provider="fly-io")
        provider = get_cloud_provider(cfg)
        self.assertIsInstance(provider, FlyIoProvider)

    def test_github_codespaces_returns_provider(self):
        cfg = CloudAgentConfig(provider="github-codespaces")
        provider = get_cloud_provider(cfg)
        self.assertIsInstance(provider, GitHubCodespacesProvider)

    def test_unknown_returns_none(self):
        cfg = CloudAgentConfig(provider="unknown-provider")
        self.assertIsNone(get_cloud_provider(cfg))


class TestFlyIoProviderLaunch(unittest.TestCase):
    def test_no_api_key_returns_error(self):
        import sys, types
        fake_aiohttp = types.ModuleType("aiohttp")
        with patch.dict(sys.modules, {"aiohttp": fake_aiohttp}):
            cfg = CloudAgentConfig(provider="fly-io", api_key="")
            provider = FlyIoProvider(cfg)
            provider._api_key = ""
            status = asyncio.run(provider.launch("a1", "do stuff", "read-only", 60))
        self.assertEqual(status.status, "failed")
        self.assertIn("FLY_API_TOKEN", status.error)


class TestCloudAgentStatus(unittest.TestCase):
    def test_fields_accessible(self):
        s = CloudAgentStatus(agent_id="a1", provider="fly-io", remote_id="r1", status="running")
        self.assertEqual(s.agent_id, "a1")
        self.assertEqual(s.provider, "fly-io")
        self.assertEqual(s.remote_id, "r1")
        self.assertEqual(s.status, "running")
        self.assertEqual(s.output, "")
        self.assertEqual(s.error, "")
        self.assertIsInstance(s.metadata, dict)


if __name__ == "__main__":
    unittest.main()
