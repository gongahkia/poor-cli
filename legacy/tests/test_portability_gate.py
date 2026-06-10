"""Tests for MH9 stateful-API portability gate."""

from __future__ import annotations

import unittest

from poor_cli.config import Config
from poor_cli.providers.portability import (
    PortabilityViolation,
    STATEFUL_FEATURES,
    enforce_portability,
    is_strict,
)


class PortabilityGateTests(unittest.TestCase):
    def test_default_is_strict(self):
        config = Config()
        self.assertTrue(config.providers_portability.strict)
        self.assertTrue(is_strict(config))

    def test_none_config_is_noop(self):
        enforce_portability("openai", "openai_responses_stateful", config=None)
        self.assertFalse(is_strict(None))

    def test_strict_blocks_known_stateful_feature(self):
        config = Config()
        with self.assertRaises(PortabilityViolation) as ctx:
            enforce_portability("openai", "openai_responses_stateful", config)
        self.assertIn("openai_responses_stateful", str(ctx.exception))
        self.assertIn("providers_portability", str(ctx.exception))

    def test_strict_blocks_unknown_feature_codes_too(self):
        config = Config()
        with self.assertRaises(PortabilityViolation):
            enforce_portability("anthropic", "some_future_feature", config)

    def test_allowed_features_opt_in(self):
        config = Config()
        config.providers_portability.allowed_stateful_features = {
            "openai": ["openai_responses_stateful"],
        }
        # allowed for openai
        enforce_portability("openai", "openai_responses_stateful", config)
        # NOT allowed for a different provider
        with self.assertRaises(PortabilityViolation):
            enforce_portability("anthropic", "openai_responses_stateful", config)

    def test_non_strict_allows_everything(self):
        config = Config()
        config.providers_portability.strict = False
        self.assertFalse(is_strict(config))
        enforce_portability("openai", "openai_responses_stateful", config)
        enforce_portability("anthropic", "anthropic_managed_agents", config)
        enforce_portability("anyone", "some_future_feature", config)

    def test_stateful_feature_catalog_documents_knowns(self):
        self.assertIn("openai_responses_stateful", STATEFUL_FEATURES)
        self.assertIn("anthropic_managed_agents", STATEFUL_FEATURES)
        self.assertIn("codex_encrypted_compaction", STATEFUL_FEATURES)


if __name__ == "__main__":
    unittest.main()
