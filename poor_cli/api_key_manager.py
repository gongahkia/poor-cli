"""
API Key Security Manager

Encrypted storage and rotation management for API keys.
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class APIKeyManager:
    """Secure API key storage and management"""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize API key manager

        Args:
            config_dir: Directory for key storage (defaults to ~/.poor-cli/keys)
        """
        self.config_dir = config_dir or (Path.home() / ".poor-cli" / "keys")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.keys_file = self.config_dir / "encrypted_keys.json"
        self.key_file = self.config_dir / ".keyfile"

        # Generate or load encryption key
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)

        logger.info(f"Initialized API key manager at {self.config_dir}")

    def _get_or_create_encryption_key(self) -> bytes:
        """Get existing or create new encryption key"""
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            # Set restrictive permissions before writing
            self.key_file.touch(mode=0o600)
            with open(self.key_file, 'wb') as f:
                f.write(key)
            logger.info("Generated new encryption key")
            return key

    def store_key(
        self,
        provider: str,
        api_key: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Store an encrypted API key

        Args:
            provider: Provider name (gemini, openai, etc.)
            api_key: API key to store
            metadata: Optional metadata (usage limits, etc.)
        """
        # Load existing keys
        keys_data = self._load_encrypted_keys()

        # Encrypt the API key
        encrypted_key = self.cipher.encrypt(api_key.encode())
        encoded_key = base64.b64encode(encrypted_key).decode()

        # Store with metadata
        keys_data[provider] = {
            "encrypted_key": encoded_key,
            "created_at": datetime.now().isoformat(),
            "last_rotated": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        # Save back
        self._save_encrypted_keys(keys_data)
        logger.info(f"Stored encrypted API key for {provider}")

    def get_key(self, provider: str) -> Optional[str]:
        """Retrieve and decrypt an API key

        Args:
            provider: Provider name

        Returns:
            Decrypted API key or None if not found
        """
        keys_data = self._load_encrypted_keys()

        if provider not in keys_data:
            logger.warning(f"No API key found for {provider}")
            return None

        try:
            encoded_key = keys_data[provider]["encrypted_key"]
            encrypted_key = base64.b64decode(encoded_key)
            decrypted_key = self.cipher.decrypt(encrypted_key).decode()
            return decrypted_key
        except Exception as e:
            logger.error(f"Failed to decrypt API key for {provider}: {e}")
            return None

    def rotate_key(self, provider: str, new_api_key: str):
        """Rotate an API key

        Args:
            provider: Provider name
            new_api_key: New API key
        """
        keys_data = self._load_encrypted_keys()

        if provider in keys_data:
            # Update rotation timestamp
            keys_data[provider]["last_rotated"] = datetime.now().isoformat()

        # Store new key
        self.store_key(provider, new_api_key, keys_data.get(provider, {}).get("metadata"))
        logger.info(f"Rotated API key for {provider}")

    def get_key_age(self, provider: str) -> Optional[int]:
        """Get age of API key in days

        Args:
            provider: Provider name

        Returns:
            Age in days or None if not found
        """
        keys_data = self._load_encrypted_keys()

        if provider not in keys_data:
            return None

        last_rotated = datetime.fromisoformat(keys_data[provider]["last_rotated"])
        age_days = (datetime.now() - last_rotated).days
        return age_days

    def check_rotation_needed(self, provider: str, rotation_days: int = 90) -> bool:
        """Check if key rotation is recommended

        Args:
            provider: Provider name
            rotation_days: Recommended rotation period in days

        Returns:
            True if rotation is recommended
        """
        age = self.get_key_age(provider)
        if age is None:
            return False

        return age >= rotation_days

    def delete_key(self, provider: str):
        """Delete an API key

        Args:
            provider: Provider name
        """
        keys_data = self._load_encrypted_keys()

        if provider in keys_data:
            del keys_data[provider]
            self._save_encrypted_keys(keys_data)
            logger.info(f"Deleted API key for {provider}")

    def list_providers(self) -> Dict[str, Dict[str, Any]]:
        """List all stored providers and their metadata

        Returns:
            Dictionary of providers and their info (excluding keys)
        """
        keys_data = self._load_encrypted_keys()

        providers_info = {}
        for provider, data in keys_data.items():
            providers_info[provider] = {
                "created_at": data["created_at"],
                "last_rotated": data["last_rotated"],
                "age_days": self.get_key_age(provider),
                "rotation_needed": self.check_rotation_needed(provider),
                "metadata": data.get("metadata", {})
            }

        return providers_info

    def _load_encrypted_keys(self) -> Dict[str, Any]:
        """Load encrypted keys from file"""
        if not self.keys_file.exists():
            return {}

        try:
            with open(self.keys_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load encrypted keys: {e}")
            return {}

    def _save_encrypted_keys(self, keys_data: Dict[str, Any]):
        """Save encrypted keys to file"""
        try:
            # Set restrictive permissions
            self.keys_file.touch(mode=0o600)
            with open(self.keys_file, 'w') as f:
                json.dump(keys_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save encrypted keys: {e}")


# Global API key manager instance
_api_key_manager: Optional[APIKeyManager] = None


def get_api_key_manager() -> APIKeyManager:
    """Get global API key manager instance"""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager
