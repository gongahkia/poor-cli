"""
Named configuration profiles for poor-cli.

Profiles are stored in ~/.poor-cli/profiles/ as YAML files.
Built-in profiles: fast, deep-review, safe, full-auto.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger, ConfigurationError

logger = setup_logger(__name__)

PROFILES_DIR = "profiles"

BUILTIN_PROFILES: Dict[str, Dict[str, Any]] = {
    "fast": {
        "_description": "Fastest responses with cheaper models",
        "model": {"routing_mode": "speed"},
        "economy": {"preset": "frugal", "terse_system_prompt": True},
        "agentic": {"max_iterations": 10},
    },
    "deep-review": {
        "_description": "Thorough review with quality models and higher iteration cap",
        "model": {"routing_mode": "quality"},
        "economy": {"preset": "quality"},
        "agentic": {"max_iterations": 50},
        "sandbox": {"default_preset": "review-only"},
    },
    "safe": {
        "_description": "Read-only sandbox with approval required for all operations",
        "sandbox": {"default_preset": "read-only"},
        "security": {"permission_mode": "prompt"},
        "agentic": {"max_iterations": 15},
    },
    "full-auto": {
        "_description": "Maximum autonomy with workspace-write and auto-safe permissions",
        "sandbox": {"default_preset": "workspace-write"},
        "security": {"permission_mode": "auto-safe"},
        "agentic": {"max_iterations": 25},
        "_auto_feedback_enabled": True,
    },
}


@dataclass
class ProfileInfo:
    """Profile metadata."""
    name: str
    description: str
    source: str # "builtin" or "user"
    overrides: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "overrides": self.overrides,
        }


class ProfileManager:
    """Manages named configuration profiles."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = (base_dir or Path.home() / ".poor-cli").resolve()
        self._profiles_dir = self._base / PROFILES_DIR

    def list_profiles(self) -> List[ProfileInfo]:
        """List all available profiles (builtin + user)."""
        profiles: List[ProfileInfo] = []
        for name, overrides in BUILTIN_PROFILES.items():
            desc = overrides.get("_description", "")
            profiles.append(ProfileInfo(name=name, description=desc, source="builtin", overrides=overrides))
        if self._profiles_dir.is_dir():
            for path in sorted(self._profiles_dir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    desc = data.pop("_description", path.stem)
                    profiles.append(ProfileInfo(
                        name=path.stem,
                        description=desc,
                        source="user",
                        overrides=data,
                    ))
                except Exception as exc:
                    logger.warning("failed to load profile %s: %s", path.name, exc)
        return profiles

    def get_profile(self, name: str) -> Optional[ProfileInfo]:
        """Get a profile by name."""
        for p in self.list_profiles():
            if p.name == name:
                return p
        return None

    def get_overrides(self, name: str) -> Dict[str, Any]:
        """Get config overrides for a named profile."""
        profile = self.get_profile(name)
        if not profile:
            raise ConfigurationError(f"unknown profile: {name}")
        overrides = dict(profile.overrides)
        overrides.pop("_description", None)
        return overrides

    def save_profile(self, name: str, description: str, overrides: Dict[str, Any]) -> ProfileInfo:
        """Save a user profile to disk."""
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        data = dict(overrides)
        data["_description"] = description
        path = self._profiles_dir / f"{name}.yaml"
        path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
        return ProfileInfo(name=name, description=description, source="user", overrides=overrides)

    def delete_profile(self, name: str) -> bool:
        """Delete a user profile. Cannot delete builtins."""
        if name in BUILTIN_PROFILES:
            raise ConfigurationError(f"cannot delete built-in profile: {name}")
        path = self._profiles_dir / f"{name}.yaml"
        if path.exists():
            path.unlink()
            return True
        return False

    def apply_to_config(self, config: Any, profile_name: str) -> None:
        """Apply profile overrides to a Config object in-place."""
        overrides = self.get_overrides(profile_name)
        from .config import ConfigManager
        ConfigManager._deep_merge(config, overrides)
        # handle top-level flags
        if "_auto_feedback_enabled" in overrides:
            config._auto_feedback_enabled = overrides["_auto_feedback_enabled"]
        logger.info("applied profile: %s", profile_name)
