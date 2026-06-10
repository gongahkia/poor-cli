# ruff: noqa: F403,F405
from __future__ import annotations

from ...config import PermissionMode, parse_permission_mode
from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class ConfigHandlersMixin:
    async def handle_get_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the current configuration for clients."""
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

    async def handle_toggle_sandbox(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Cycle or set the active sandbox preset."""
        self._ensure_initialized()
        presets = ("read-only", "review-only", "workspace-write", "full-access")
        requested = params.get("preset") or params.get("sandboxPreset")
        current = self._current_sandbox_preset()
        if requested is None:
            next_preset = presets[(presets.index(current) + 1) % len(presets)] if current in presets else "workspace-write"
        else:
            next_preset = normalize_preset(str(requested), fallback_permission_mode=self.permission_mode)
        if self.core.config is not None and getattr(self.core.config, "sandbox", None) is not None:
            self.core.config.sandbox.default_preset = next_preset
        self._sandbox_preset = next_preset
        self.permission_mode = permission_mode_from_preset(next_preset)
        if self.core.config is not None and getattr(self.core.config, "security", None) is not None:
            self.core.config.security.permission_mode = parse_permission_mode(self.permission_mode)
        if getattr(self.core, "_config_manager", None) is not None:
            self.core._config_manager.config = self.core.config
            self.core._config_manager.save()
        return {
            "sandboxPreset": self._current_sandbox_preset(),
            "permissionMode": self.permission_mode,
        }

    def _flatten_config_values(self, value: Any, prefix: str, output: List[Dict[str, Any]]) -> None:
        """Flatten nested dict/list/scalars into a dot-path list with choices metadata."""
        if isinstance(value, dict):
            for key in sorted(value.keys()):
                next_prefix = f"{prefix}.{key}" if prefix else key
                self._flatten_config_values(value[key], next_prefix, output)
            return

        if isinstance(value, list):
            output.append(
                {
                    "path": prefix,
                    "value": value,
                    "type": "list",
                    "isBoolean": False,
                }
            )
            return

        if isinstance(value, bool):
            value_type = "bool"
        elif isinstance(value, int):
            value_type = "int"
        elif isinstance(value, float):
            value_type = "float"
        elif value is None:
            value_type = "null"
        else:
            value_type = "string"

        entry: Dict[str, Any] = {
            "path": prefix,
            "value": value,
            "type": value_type,
            "isBoolean": isinstance(value, bool),
        }
        if prefix in self._CHOICES_MAP:
            entry["choices"] = self._CHOICES_MAP[prefix]
        output.append(entry)

    def _resolve_config_parent(self, key_path: str) -> Tuple[Any, str]:
        keys = [k for k in key_path.split(".") if k]
        if not keys:
            raise InvalidParamsError("Invalid keyPath")

        current: Any = self.core.config
        for key in keys[:-1]:
            if isinstance(current, dict):
                if key not in current:
                    raise InvalidParamsError(f"Unknown config path: {key_path}")
                current = current[key]
            elif hasattr(current, key):
                current = getattr(current, key)
            else:
                raise InvalidParamsError(f"Unknown config path: {key_path}")

        return current, keys[-1]

    def _get_config_value(self, key_path: str) -> Any:
        parent, final_key = self._resolve_config_parent(key_path)
        if isinstance(parent, dict):
            if final_key not in parent:
                raise InvalidParamsError(f"Unknown config key: {key_path}")
            return parent[final_key]
        if hasattr(parent, final_key):
            return getattr(parent, final_key)
        raise InvalidParamsError(f"Unknown config key: {key_path}")

    def _set_config_value(self, key_path: str, value: Any) -> None:
        parent, final_key = self._resolve_config_parent(key_path)
        if isinstance(parent, dict):
            parent[final_key] = value
            return
        if hasattr(parent, final_key):
            setattr(parent, final_key, value)
            return
        raise InvalidParamsError(f"Unknown config key: {key_path}")

    def _coerce_config_value(self, current: Any, proposed: Any, key_path: str) -> Any:
        if isinstance(current, Enum):
            enum_cls = type(current)
            if isinstance(proposed, str):
                try:
                    return enum_cls(proposed)
                except ValueError as e:
                    raise InvalidParamsError(f"Invalid value for {key_path}: {proposed}") from e
            raise InvalidParamsError(f"{key_path} expects a string enum value")

        if isinstance(current, bool):
            if isinstance(proposed, bool):
                return proposed
            if isinstance(proposed, str):
                normalized = proposed.strip().lower()
                if normalized in {"1", "true", "yes", "on", "enabled"}:
                    return True
                if normalized in {"0", "false", "no", "off", "disabled"}:
                    return False
            raise InvalidParamsError(f"{key_path} expects a boolean value")

        if isinstance(current, int) and not isinstance(current, bool):
            if isinstance(proposed, (int, float)):
                return int(proposed)
            if isinstance(proposed, str):
                try:
                    return int(proposed.strip())
                except ValueError as e:
                    raise InvalidParamsError(f"{key_path} expects an integer value") from e
            raise InvalidParamsError(f"{key_path} expects an integer value")

        if isinstance(current, float):
            if isinstance(proposed, (int, float)):
                return float(proposed)
            if isinstance(proposed, str):
                try:
                    return float(proposed.strip())
                except ValueError as e:
                    raise InvalidParamsError(f"{key_path} expects a float value") from e
            raise InvalidParamsError(f"{key_path} expects a float value")

        if isinstance(current, list):
            if isinstance(proposed, list):
                return proposed
            if isinstance(proposed, str):
                candidate = proposed.strip()
                if candidate.startswith("["):
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError as e:
                        raise InvalidParamsError(f"{key_path} expects a JSON list") from e
                    if isinstance(parsed, list):
                        return parsed
                    raise InvalidParamsError(f"{key_path} expects a JSON list")
                if candidate == "":
                    return []
                return [part.strip() for part in candidate.split(",") if part.strip()]
            raise InvalidParamsError(f"{key_path} expects a list value")

        if isinstance(current, dict):
            if isinstance(proposed, dict):
                return proposed
            if isinstance(proposed, str):
                try:
                    parsed = json.loads(proposed.strip())
                except json.JSONDecodeError as e:
                    raise InvalidParamsError(f"{key_path} expects a JSON object") from e
                if isinstance(parsed, dict):
                    return parsed
            raise InvalidParamsError(f"{key_path} expects an object value")

        if current is None:
            return proposed

        return str(proposed)

    def _jsonable_value(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        return value

@register('getConfig')
async def _rpc_6(ctx, params):
    return await ctx.handle_get_config(params)

@register('setConfig')
async def _rpc_7(ctx, params):
    return await ctx.handle_set_config(params)

@register('getPermissions')
async def _rpc_8(ctx, params):
    return await ctx.handle_get_permissions(params)

@register('setPermissions')
async def _rpc_9(ctx, params):
    return await ctx.handle_set_permissions(params)

@register('poor-cli/listConfigOptions')
async def _rpc_40(ctx, params):
    return await ctx.handle_list_config_options(params)

@register('poor-cli/setConfig')
async def _rpc_41(ctx, params):
    return await ctx.handle_set_config(params)

@register('poor-cli/getPermissions')
async def _rpc_42(ctx, params):
    return await ctx.handle_get_permissions(params)

@register('poor-cli/setPermissions')
async def _rpc_43(ctx, params):
    return await ctx.handle_set_permissions(params)

@register('poor-cli/toggleConfig')
async def _rpc_44(ctx, params):
    return await ctx.handle_toggle_config(params)

@register('sandbox/toggle')
async def _rpc_sandbox_toggle(ctx, params):
    return await ctx.handle_toggle_sandbox(params)

@register('permissions/list')
async def _rpc_permissions_list(ctx, params):
    return await ctx.handle_get_permissions(params)
