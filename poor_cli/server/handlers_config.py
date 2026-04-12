"""Config/permissions RPC handlers, split out of runtime.py.

These are implemented as a mixin on PoorCLIServer. All methods access
PoorCLIServer internals (self.core, self.permission_mode, etc.) via
duck typing — the mixin is only valid when combined with the main
server class.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from ..config import PermissionMode
from ..exceptions import ConfigurationError
from ..sandbox import (
    normalize_preset,
    permission_mode_from_preset,
    preset_from_permission_mode,
)
from ..config import parse_permission_mode
from .types import InvalidParamsError


class ConfigHandlersMixin:
    """Handlers for get/set config, permissions, and option listing."""

    async def handle_get_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the current configuration for the Rust TUI."""
        self._ensure_initialized()
        config = self.core.config
        if config is None:
            raise RuntimeError("Core configuration unavailable")
        provider_info = self.core.get_provider_info()
        config_path = None
        if self.core._config_manager is not None:
            config_path = str(self.core._config_manager.config_path)
        return {
            "provider": provider_info.get("name", "unknown"),
            "model": provider_info.get("model", "unknown"),
            "theme": config.ui.theme,
            "streaming": config.ui.enable_streaming,
            "showTokenCount": config.ui.show_token_count,
            "markdownRendering": config.ui.markdown_rendering,
            "showToolCalls": config.ui.show_tool_calls,
            "verboseLogging": config.ui.verbose_logging,
            "planMode": config.plan_mode.enabled,
            "checkpointing": config.checkpoint.enabled,
            "version": getattr(self.core, "_version", "0.4.0"),
            "permissionMode": self.permission_mode,
            "sandboxPreset": self._current_sandbox_preset(),
            "configFile": config_path,
        }

    async def handle_get_permissions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return current permission mode and effective rule scopes."""
        del params
        self._ensure_initialized()
        return {
            "permissionMode": self.permission_mode,
            "sandboxPreset": self._current_sandbox_preset(),
            "rules": self._permission_rules.list_rules(),
        }

    async def handle_set_permissions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update permission mode and/or permission rules."""
        self._ensure_initialized()
        if self.core.config is None:
            raise RuntimeError("Core configuration unavailable")

        mode = params.get("mode")
        if mode is not None:
            try:
                parsed_mode = parse_permission_mode(mode)
            except ConfigurationError:
                raise InvalidParamsError(
                    "Invalid mode. Expected one of: default, acceptEdits, plan, bypassPermissions, "
                    "dontAsk, prompt, auto-safe, danger-full-access."
                )
            self.permission_mode = parsed_mode.value
            self.core.config.security.permission_mode = parsed_mode
            self._sandbox_preset = preset_from_permission_mode(self.permission_mode)
            if self.core._config_manager is not None:
                self.core._config_manager.config = self.core.config
                self.core._config_manager.save()

        if bool(params.get("clearSessionRules", False)):
            self._permission_rules.clear_session_rules()

        add_rule = params.get("addRule")
        if isinstance(add_rule, dict):
            scope = str(add_rule.get("scope", "session")).strip().lower() or "session"
            tool_name = str(add_rule.get("toolName") or add_rule.get("tool_name") or "").strip()
            behavior = str(add_rule.get("behavior", "ask")).strip().lower()
            rule_content = str(add_rule.get("ruleContent") or add_rule.get("rule_content") or "").strip()
            if not tool_name:
                raise InvalidParamsError("addRule.toolName is required")
            if scope == "session":
                self._permission_rules.add_session_rule(
                    tool_name=tool_name,
                    behavior=behavior,
                    rule_content=rule_content,
                )
            else:
                self._permission_rules.add_persistent_rule(
                    scope=scope,
                    tool_name=tool_name,
                    behavior=behavior,
                    rule_content=rule_content,
                )

        await self._sync_provider_tool_visibility()

        return {
            "permissionMode": self.permission_mode,
            "sandboxPreset": self._current_sandbox_preset(),
            "rules": self._permission_rules.list_rules(),
        }

    async def handle_list_config_options(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List editable config leaf values in dot-notation form."""
        del params
        self._ensure_initialized()
        if self.core.config is None:
            raise RuntimeError("Core configuration unavailable")

        options: List[Dict[str, Any]] = []
        self._flatten_config_values(self.core.config.to_dict(), "", options)
        options.sort(key=lambda item: item["path"])

        config_path = None
        if self.core._config_manager is not None:
            config_path = str(self.core._config_manager.config_path)

        return {
            "options": options,
            "permissionMode": self.permission_mode,
            "configFile": config_path,
        }

    async def handle_set_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set a config value by keyPath."""
        self._ensure_initialized()
        if self.core.config is None:
            raise RuntimeError("Core configuration unavailable")
        if self.core._config_manager is None:
            raise RuntimeError("Config manager unavailable")

        key_path = str(params.get("keyPath", "")).strip()
        if not key_path:
            raise InvalidParamsError("Missing keyPath")
        if "value" not in params:
            raise InvalidParamsError("Missing value")

        old_value = copy.deepcopy(self._get_config_value(key_path))
        new_value = self._coerce_config_value(old_value, params["value"], key_path)
        self._set_config_value(key_path, new_value)

        provider_switched = False
        try:
            if key_path in {"model.provider", "model.model_name"}:
                provider_name = self.core.config.model.provider
                model_name = self.core.config.model.model_name
                await self.core.switch_provider(provider_name, model_name)
                provider_switched = True
            elif key_path.startswith("mcp_servers."):
                await self.core.reload_mcp_servers()

            if key_path == "security.permission_mode":
                mode = self.core.config.security.permission_mode
                if isinstance(mode, PermissionMode):
                    self.permission_mode = mode.value
                else:
                    self.permission_mode = str(mode)
                self._sandbox_preset = preset_from_permission_mode(self.permission_mode)
            if key_path == "sandbox.default_preset":
                self._sandbox_preset = normalize_preset(
                    self.core.config.sandbox.default_preset,
                    fallback_permission_mode=self.permission_mode,
                )
                self.permission_mode = permission_mode_from_preset(self._sandbox_preset)

            self.core._config_manager.config = self.core.config
            self.core._config_manager.validate()
            self.core._config_manager.save()
        except Exception:
            self._set_config_value(key_path, old_value)
            if key_path == "security.permission_mode":
                mode = self.core.config.security.permission_mode
                self.permission_mode = mode.value if isinstance(mode, PermissionMode) else str(mode)
                self._sandbox_preset = preset_from_permission_mode(self.permission_mode)
            if key_path == "sandbox.default_preset":
                self._sandbox_preset = normalize_preset(
                    self.core.config.sandbox.default_preset,
                    fallback_permission_mode=self.permission_mode,
                )
            raise

        return {
            "success": True,
            "keyPath": key_path,
            "value": self._jsonable_value(self._get_config_value(key_path)),
            "providerSwitched": provider_switched,
        }

    async def handle_toggle_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Toggle a boolean config key by keyPath."""
        self._ensure_initialized()
        key_path = str(params.get("keyPath", "")).strip()
        if not key_path:
            raise InvalidParamsError("Missing keyPath")

        current = self._get_config_value(key_path)
        if not isinstance(current, bool):
            raise InvalidParamsError(f"{key_path} is not a boolean value")

        return await self.handle_set_config(
            {
                "keyPath": key_path,
                "value": not current,
            }
        )
