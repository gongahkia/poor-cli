import unittest

from poor_cli import credentials
from poor_cli.config import Config, ConfigManager
from poor_cli.credentials import CredentialStore, SERVICE_NAME


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, password):
        self.values[(service, username)] = password


class FailingKeyring:
    def get_password(self, service, username):
        raise RuntimeError("no backend")

    def set_password(self, service, username, password):
        raise RuntimeError("no backend")


class TestKeyringCredentials(unittest.TestCase):
    def test_lookup_order_keyring_env_config(self):
        env = {"OPENAI_API_KEY": "env-key"}
        config = {"openai": "config-key"}
        keyring = FakeKeyring()
        keyring.set_password(SERVICE_NAME, "openai", "keyring-key")
        store = CredentialStore(keyring_backend=keyring, env=env)

        lookup = store.get_with_source("openai", env_var="OPENAI_API_KEY", config_keys=config)

        self.assertEqual(lookup.key, "keyring-key")
        self.assertEqual(lookup.source, "keyring")

    def test_lookup_falls_back_to_env(self):
        env = {"OPENAI_API_KEY": "env-key"}
        config = {"openai": "config-key"}
        store = CredentialStore(keyring_backend=FakeKeyring(), env=env)

        lookup = store.get_with_source("openai", env_var="OPENAI_API_KEY", config_keys=config)

        self.assertEqual(lookup.key, "env-key")
        self.assertEqual(lookup.source, "environment")

    def test_lookup_falls_back_to_plaintext_config(self):
        store = CredentialStore(keyring_backend=FakeKeyring(), env={})

        lookup = store.get_with_source("openai", env_var="OPENAI_API_KEY", config_keys={"openai": "config-key"})

        self.assertEqual(lookup.key, "config-key")
        self.assertEqual(lookup.source, "config")

    def test_migration_moves_env_and_config_to_keyring(self):
        keyring = FakeKeyring()
        store = CredentialStore(keyring_backend=keyring, env={"OPENAI_API_KEY": "env-key"})
        provider_env_vars = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}

        migrated = store.migrate_to_keyring(
            config_keys={"anthropic": "config-key"},
            provider_env_vars=provider_env_vars,
        )

        self.assertEqual(migrated, ["openai", "anthropic"])
        self.assertEqual(keyring.get_password(SERVICE_NAME, "openai"), "env-key")
        self.assertEqual(keyring.get_password(SERVICE_NAME, "anthropic"), "config-key")

    def test_set_rejects_empty_keys(self):
        store = CredentialStore(keyring_backend=FakeKeyring(), env={})

        with self.assertRaises(ValueError):
            store.set("openai", "", store="keyring")

    def test_unavailable_keyring_silently_falls_back(self):
        store = CredentialStore(keyring_backend=FailingKeyring(), env={"OPENAI_API_KEY": "env-key"})

        lookup = store.get_with_source("openai", env_var="OPENAI_API_KEY", config_keys={"openai": "config-key"})

        self.assertEqual(lookup.key, "env-key")
        self.assertEqual(lookup.source, "environment")
        self.assertFalse(store.status()["available"])

    def test_config_manager_uses_credential_store(self):
        old_store = credentials._credential_store
        try:
            keyring = FakeKeyring()
            keyring.set_password(SERVICE_NAME, "openai", "keyring-key")
            credentials._credential_store = CredentialStore(
                keyring_backend=keyring,
                env={"OPENAI_API_KEY": "env-key"},
            )
            manager = ConfigManager()
            manager.config = Config()
            manager.config.api_keys = {"openai": "config-key"}

            info = manager.get_api_key_info("openai")

            self.assertEqual(info["key"], "keyring-key")
            self.assertEqual(info["source"], "keyring")
        finally:
            credentials._credential_store = old_store


if __name__ == "__main__":
    unittest.main()
