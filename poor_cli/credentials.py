"""Credential lookup for provider API keys."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal, Mapping, MutableMapping, Optional

from .exceptions import setup_logger
from .provider_catalog import canonical_provider_name, provider_catalog

logger = setup_logger(__name__)

SERVICE_NAME = "poor-cli"
QA_KEYRING_BACKENDS = {
    "darwin": "macOS Keychain",
    "linux": "Secret Service",
    "win32": "Windows Credential Manager",
}
_AUTO = object()
_keyring_unavailable_logged = False


@dataclass(frozen=True)
class CredentialLookup:
    key: Optional[str]
    source: Literal["keyring", "environment", "config", "none"]


class CredentialStore:
    def __init__(
        self,
        *,
        keyring_backend: Any = _AUTO,
        env: Optional[MutableMapping[str, str]] = None,
    ) -> None:
        self._env = env if env is not None else os.environ
        self._keyring = None
        self._keyring_checked = False
        self._keyring_importable = False
        self._keyring_available = False
        self._keyring_error = ""
        if keyring_backend is not _AUTO:
            self._keyring = keyring_backend
            self._keyring_checked = True
            self._keyring_importable = keyring_backend is not None
            self._keyring_available = keyring_backend is not None

    def get(self, provider: str, *, env_var: str = "", config_keys: Optional[Mapping[str, str]] = None) -> Optional[str]:
        return self.get_with_source(provider, env_var=env_var, config_keys=config_keys).key

    def get_with_source(
        self,
        provider: str,
        *,
        env_var: str = "",
        config_keys: Optional[Mapping[str, str]] = None,
    ) -> CredentialLookup:
        provider = canonical_provider_name(provider)
        key = self._get_keyring(provider)
        if key:
            return CredentialLookup(key, "keyring")
        if env_var:
            key = str(self._env.get(env_var, "") or "").strip()
            if key:
                return CredentialLookup(key, "environment")
        if config_keys:
            key = str(config_keys.get(provider, "") or "").strip()
            if key:
                return CredentialLookup(key, "config")
        return CredentialLookup(None, "none")

    def set(
        self,
        provider: str,
        key: str,
        *,
        store: Literal["keyring", "env", "config"] = "keyring",
        env_var: str = "",
        config_keys: Optional[MutableMapping[str, str]] = None,
    ) -> Optional[str]:
        provider = canonical_provider_name(provider)
        key = str(key or "").strip()
        if not key:
            raise ValueError("API key cannot be empty")
        if store == "keyring":
            kr = self._load_keyring()
            if kr is None:
                return None
            try:
                kr.set_password(SERVICE_NAME, provider, key)
                return "keyring"
            except Exception as exc:
                self._disable_keyring(exc)
                return None
        if store == "env":
            if not env_var:
                raise ValueError("env_var is required for env storage")
            self._env[env_var] = key
            return "environment"
        if store == "config":
            if config_keys is None:
                raise ValueError("config_keys is required for config storage")
            config_keys[provider] = key
            return "config"
        raise ValueError(f"unknown credential store: {store}")

    def migrate_to_keyring(
        self,
        *,
        config_keys: Optional[Mapping[str, str]] = None,
        provider_env_vars: Optional[Mapping[str, str]] = None,
    ) -> list[str]:
        if self._load_keyring() is None:
            return []
        migrated: list[str] = []
        for provider, env_var in (provider_env_vars or provider_env_var_map()).items():
            if provider == "ollama":
                continue
            lookup = self.get_with_source(provider, env_var=env_var, config_keys=config_keys)
            if lookup.source not in {"environment", "config"} or not lookup.key:
                continue
            if self.set(provider, lookup.key, store="keyring") == "keyring":
                migrated.append(provider)
        return migrated

    def migration_candidates(
        self,
        *,
        config_keys: Optional[Mapping[str, str]] = None,
        provider_env_vars: Optional[Mapping[str, str]] = None,
    ) -> list[str]:
        if self._load_keyring() is None:
            return []
        candidates: list[str] = []
        for provider, env_var in (provider_env_vars or provider_env_var_map()).items():
            if provider == "ollama":
                continue
            if self._get_keyring(provider):
                continue
            if not self._keyring_available:
                return []
            lookup = self.get_with_source(provider, env_var=env_var, config_keys=config_keys)
            if lookup.source in {"environment", "config"} and lookup.key:
                candidates.append(provider)
        return candidates

    def status(self) -> dict[str, Any]:
        kr = self._load_keyring()
        backend = ""
        if kr is not None:
            backend_obj = kr
            try:
                if hasattr(kr, "get_keyring"):
                    backend_obj = kr.get_keyring()
            except Exception:
                backend_obj = kr
            backend = backend_obj.__class__.__name__
        return {
            "service": SERVICE_NAME,
            "importable": self._keyring_importable,
            "available": kr is not None and self._keyring_available,
            "backend": backend,
            "error": self._keyring_error,
            "qaBackends": dict(QA_KEYRING_BACKENDS),
        }

    def _get_keyring(self, provider: str) -> Optional[str]:
        kr = self._load_keyring()
        if kr is None:
            return None
        try:
            return kr.get_password(SERVICE_NAME, provider)
        except Exception as exc:
            self._disable_keyring(exc)
            return None

    def _load_keyring(self) -> Any:
        if not self._keyring_checked:
            self._keyring_checked = True
            try:
                import keyring

                self._keyring = keyring
                self._keyring_importable = True
                self._keyring_available = True
            except Exception as exc:
                self._keyring = None
                self._keyring_importable = False
                self._disable_keyring(exc)
        return self._keyring if self._keyring_available else None

    def _disable_keyring(self, exc: Exception) -> None:
        global _keyring_unavailable_logged
        self._keyring_available = False
        self._keyring_error = exc.__class__.__name__
        if not _keyring_unavailable_logged:
            logger.info("OS keyring unavailable; using env/config credential fallback")
            _keyring_unavailable_logged = True


def provider_env_var_map() -> dict[str, str]:
    return {name: entry.env_var for name, entry in provider_catalog().items()}


_credential_store: Optional[CredentialStore] = None


def get_credential_store() -> CredentialStore:
    global _credential_store
    if _credential_store is None:
        _credential_store = CredentialStore()
    return _credential_store
