from __future__ import annotations

import json
import os
import tomllib
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

from .fusion import fusion_summary
from .route_policy import classify_goal_text

VERSION = 1
ROLE_NAMES = ("planner", "executor", "reviewer", "verifier", "fallback", "researcher", "graph_navigator")
LOCAL_KINDS = {"ollama", "vllm", "sglang"}
COMPATIBLE_KINDS = {"openai-compatible", "openrouter", "kimi", "vllm", "sglang"}
SECRET_FIELDS = {"api_key", "apikey", "token", "secret", "password", "bearer"}


class ConfigError(RuntimeError):
    pass


def repo_config_path(repo: Path | None = None) -> Path:
    return (repo or Path.cwd()) / ".poor-cli" / "config.toml"


def user_config_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return root / "poor-cli" / "config.toml"


def empty_config() -> dict[str, Any]:
    return {
        "version": VERSION,
        "active_provider": "",
        "providers": {},
        "models": {},
        "routes": {},
        "budgets": {},
        "tools": {},
        "concurrency": {},
    }


def load_config(repo: Path | None = None, *, include_env: bool = True) -> dict[str, Any]:
    config = empty_config()
    for path in (user_config_path(), repo_config_path(repo)):
        if path.exists():
            config = _merge(config, _read_config(path))
    if include_env:
        config = _merge(config, env_config())
    validate_config(config)
    return config


def parse_config_text(text: str, *, source: str = "<config>") -> dict[str, Any]:
    try:
        data = json.loads(text) if text.lstrip().startswith("{") else tomllib.loads(text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid config {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"config {source} must decode to an object")
    validate_config(data)
    return data


def save_repo_config(config: dict[str, Any], repo: Path | None = None) -> Path:
    validate_config(config)
    path = repo_config_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_toml(config), encoding="utf-8")
    return path


def provider_preset(
    kind: str,
    *,
    profile_id: str,
    model: str | None = None,
    base_url: str | None = None,
    auth_env: str | None = None,
) -> dict[str, Any]:
    kind = kind.strip().lower()
    if kind == "kimi" and not model:
        model = "kimi-k2.7-code"
    profile: dict[str, Any] = {"kind": kind, "models": [model] if model else [], "capabilities": _capabilities(kind)}
    if base_url:
        profile["base_url"] = base_url.rstrip("/")
    elif kind == "openai":
        profile["base_url"] = "https://api.openai.com/v1"
    elif kind == "openrouter":
        profile["base_url"] = "https://openrouter.ai/api/v1"
    elif kind == "kimi":
        profile["base_url"] = "https://api.moonshot.ai/v1"
    elif kind == "ollama":
        profile["base_url"] = "http://localhost:11434"
    elif kind == "vllm":
        profile["base_url"] = "http://localhost:8000"
    elif kind == "sglang":
        profile["base_url"] = "http://localhost:30000"
    if auth_env:
        profile["auth"] = {"env": auth_env}
    elif kind == "openai":
        profile["auth"] = {"env": "OPENAI_API_KEY"}
    elif kind == "openrouter":
        profile["auth"] = {"env": "OPENROUTER_API_KEY"}
    elif kind == "kimi":
        profile["auth"] = {"env": "MOONSHOT_API_KEY"}
    if not profile["models"] and kind not in {"ollama"}:
        raise ConfigError(f"--model is required for {kind}")
    return {profile_id: profile}


def add_provider(config: dict[str, Any], profile_id: str, profile: dict[str, Any], *, make_active: bool = True) -> dict[str, Any]:
    next_config = deepcopy(config)
    next_config.setdefault("providers", {})[profile_id] = profile
    if make_active:
        next_config["active_provider"] = profile_id
        executor = next_config.setdefault("routes", {}).setdefault("executor", {})
        executor.setdefault("profile", profile_id)
        models = profile.get("models")
        if isinstance(models, list) and models:
            executor.setdefault("model", str(models[0]))
    validate_config(next_config)
    return next_config


def switch_provider(config: dict[str, Any], profile_id: str) -> dict[str, Any]:
    if profile_id not in config.get("providers", {}):
        raise ConfigError(f"profile not found: {profile_id}")
    next_config = deepcopy(config)
    next_config["active_provider"] = profile_id
    next_config.setdefault("routes", {}).setdefault("executor", {})["profile"] = profile_id
    models = next_config["providers"][profile_id].get("models")
    if isinstance(models, list) and models:
        next_config["routes"]["executor"].setdefault("model", str(models[0]))
    return next_config


def set_route(config: dict[str, Any], role: str, profile_id: str, model: str | None = None) -> dict[str, Any]:
    if role not in ROLE_NAMES:
        raise ConfigError(f"unsupported route role: {role}")
    if profile_id not in config.get("providers", {}):
        raise ConfigError(f"profile not found: {profile_id}")
    next_config = deepcopy(config)
    route = next_config.setdefault("routes", {}).setdefault(role, {})
    route["profile"] = profile_id
    if model:
        route["model"] = model
    elif not route.get("model"):
        models = next_config["providers"][profile_id].get("models")
        if isinstance(models, list) and models:
            route["model"] = str(models[0])
    validate_config(next_config)
    return next_config


def export_config(config: dict[str, Any], profile_id: str | None = None) -> dict[str, Any]:
    validate_config(config)
    exported = empty_config()
    if profile_id is None:
        for key in ("active_provider", "providers", "models", "routes", "budgets", "tools", "concurrency"):
            exported[key] = deepcopy(config.get(key, exported.get(key)))
        return exported
    providers = config.get("providers", {})
    if profile_id not in providers:
        raise ConfigError(f"profile not found: {profile_id}")
    exported["active_provider"] = profile_id if config.get("active_provider") == profile_id else ""
    exported["providers"] = {profile_id: deepcopy(providers[profile_id])}
    exported["models"] = {
        alias: deepcopy(spec)
        for alias, spec in config.get("models", {}).items()
        if isinstance(spec, dict) and spec.get("profile") == profile_id
    }
    exported["routes"] = {
        role: deepcopy(route)
        for role, route in config.get("routes", {}).items()
        if isinstance(route, dict) and route.get("profile") == profile_id
    }
    return exported


def import_config(config: dict[str, Any], imported: dict[str, Any]) -> dict[str, Any]:
    validate_config(imported)
    merged = _merge(config, imported)
    validate_config(merged)
    return merged


def provider_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    active = str(config.get("active_provider") or "")
    rows = []
    for profile_id, profile in sorted(config.get("providers", {}).items()):
        caps = profile.get("capabilities") if isinstance(profile, dict) else {}
        models = profile.get("models") if isinstance(profile, dict) else []
        rows.append(
            {
                "id": profile_id,
                "active": profile_id == active,
                "kind": str(profile.get("kind") or ""),
                "model": str(models[0]) if isinstance(models, list) and models else "",
                "base_url": _host(str(profile.get("base_url") or "")),
                "tools": bool(caps.get("tools")) if isinstance(caps, dict) else False,
                "web": bool(caps.get("web")) if isinstance(caps, dict) else False,
                "health": "configured",
            }
        )
    return rows


def model_registry(config: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for alias, spec in sorted(config.get("models", {}).items()):
        if isinstance(spec, dict):
            rows.append({"alias": alias, "profile": str(spec.get("profile") or ""), "model": str(spec.get("model") or "")})
    for profile_id, profile in sorted(config.get("providers", {}).items()):
        models = profile.get("models") if isinstance(profile, dict) else []
        if isinstance(models, list):
            rows.extend({"alias": f"{profile_id}:{model}", "profile": profile_id, "model": str(model)} for model in models)
    return rows


def doctor(config: dict[str, Any], profile_id: str, *, opener: Any | None = None) -> dict[str, Any]:
    profiles = config.get("providers", {})
    if profile_id not in profiles:
        raise ConfigError(f"profile not found: {profile_id}")
    profile = profiles[profile_id]
    auth = profile.get("auth") if isinstance(profile, dict) else {}
    auth_env = str(auth.get("env") or "") if isinstance(auth, dict) else ""
    models = profile.get("models") if isinstance(profile, dict) else []
    result: dict[str, Any] = {
        "profile": profile_id,
        "kind": str(profile.get("kind") or ""),
        "auth": {"ref": f"env:{auth_env}" if auth_env else "", "present": bool(auth_env and os.environ.get(auth_env))},
        "models": models if isinstance(models, list) else [],
        "endpoint": "not_checked",
        "model_exists": None,
        "capabilities": profile.get("capabilities") if isinstance(profile, dict) else {},
    }
    discovered = _discover_models(profile, opener=opener)
    result["endpoint"] = discovered["status"]
    if discovered["models"]:
        result["discovered_models"] = discovered["models"]
        expected = set(str(item) for item in result["models"])
        result["model_exists"] = bool(expected & set(discovered["models"])) if expected else None
    elif result["kind"] in LOCAL_KINDS | COMPATIBLE_KINDS | {"openai"}:
        result["error"] = discovered.get("error", "")
    return result


def explain_route(config: dict[str, Any], task: str, *, role: str = "executor") -> dict[str, Any]:
    routes = config.get("routes", {})
    providers = config.get("providers", {})
    route = routes.get(role) if isinstance(routes, dict) else None
    fallbacks = []
    reason = "configured route"
    if not isinstance(route, dict):
        active = str(config.get("active_provider") or "")
        route = {"profile": active} if active else {}
        reason = "active provider fallback" if active else "no route configured"
    profile_id = str(route.get("profile") or "")
    model = str(route.get("model") or "")
    if model in config.get("models", {}):
        alias = config["models"][model]
        profile_id = str(alias.get("profile") or profile_id)
        model = str(alias.get("model") or model)
        reason = "model alias"
    if profile_id not in providers:
        fallbacks.append({"profile": profile_id, "reason": "missing profile"})
        profile_id, model, reason = _first_profile(providers), "", "fallback to first configured profile"
    if profile_id and not model:
        models = providers[profile_id].get("models")
        if isinstance(models, list) and models:
            model = str(models[0])
    max_cost = route.get("max_cost_usd")
    budget_max = config.get("budgets", {}).get("max_usd")
    if profile_id and isinstance(max_cost, int | float) and isinstance(budget_max, int | float) and max_cost > budget_max:
        fallbacks.append({"profile": profile_id, "reason": "over budget"})
        profile_id, reason = str(route.get("fallback_profile") or _first_profile(providers)), "budget fallback"
    if profile_id and _rate_limited(providers.get(profile_id, {})):
        fallbacks.append({"profile": profile_id, "reason": "rate limit unavailable"})
        profile_id, reason = _first_profile_where(providers, lambda item: not _rate_limited(item)), "rate-limit fallback"
    capability = str(route.get("required_capability") or route.get("capability") or "")
    if profile_id and capability and not _has_capability(providers.get(profile_id, {}), capability):
        fallbacks.append({"profile": profile_id, "reason": f"missing capability: {capability}"})
        profile_id = _first_profile_where(providers, lambda item: _has_capability(item, capability))
        reason = "capability fallback" if profile_id else "no capable profile"
        if profile_id:
            models = providers[profile_id].get("models")
            model = str(models[0]) if isinstance(models, list) and models else ""
    if profile_id and fallbacks:
        models = providers[profile_id].get("models")
        if isinstance(models, list) and models:
            model = str(models[0])
    result = {
        "role": role,
        "task": task,
        "profile": profile_id,
        "model": model,
        "provider_kind": str(providers.get(profile_id, {}).get("kind") or ""),
        "reason": reason,
        "fallbacks": fallbacks,
        "policy": classify_goal_text(task, role=role),
        "estimated_budget": {"max_usd": route.get("max_cost_usd") or config.get("budgets", {}).get("max_usd")},
    }
    result["fusion"] = fusion_summary(providers.get(profile_id, {}), route, role) if isinstance(route, dict) else {}
    return result


def env_config() -> dict[str, Any]:
    provider = (os.environ.get("POOR_CLI_PROVIDER") or os.environ.get("POOR_CLI_LOCAL_ENGINE") or "").strip().lower()
    model = (os.environ.get("POOR_CLI_MODEL") or os.environ.get("POOR_CLI_LOCAL_MODEL") or "").strip()
    if not provider or not model:
        return empty_config()
    base_url = os.environ.get("POOR_CLI_LOCAL_BASE_URL")
    profile = provider_preset(provider, profile_id="env", model=model, base_url=base_url)
    config = empty_config()
    config["providers"] = profile
    config["active_provider"] = "env"
    config["routes"] = {"executor": {"profile": "env", "model": model}}
    return config


def validate_config(config: dict[str, Any]) -> None:
    if int(config.get("version") or 0) != VERSION:
        raise ConfigError("config version must be 1")
    _reject_plaintext_secrets(config)
    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        raise ConfigError("providers must be a table")
    for profile_id, profile in providers.items():
        if not isinstance(profile, dict):
            raise ConfigError(f"provider {profile_id} must be a table")
        kind = str(profile.get("kind") or "")
        if kind not in {"openai", "anthropic", "gemini", "ollama", "openai-compatible", "vllm", "sglang", "openrouter", "kimi"}:
            raise ConfigError(f"unsupported provider kind: {kind}")
        models = profile.get("models", [])
        if not isinstance(models, list) or any(not isinstance(item, str) or not item for item in models):
            raise ConfigError(f"provider {profile_id} models must be a string list")


def to_toml(config: dict[str, Any]) -> str:
    lines = [f"version = {VERSION}"]
    if config.get("active_provider"):
        lines.append(f"active_provider = {_toml_value(config['active_provider'])}")
    for section in ("providers", "models", "routes", "budgets", "tools", "concurrency"):
        value = config.get(section)
        if isinstance(value, dict):
            _write_section(lines, section, value)
    return "\n".join(lines).rstrip() + "\n"


def _read_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config {path}: {exc}") from exc
    if "version" not in data:
        raise ConfigError(f"config {path} missing version")
    return dict(data)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        elif value not in ("", None):
            result[key] = deepcopy(value)
    return result


def _reject_plaintext_secrets(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in SECRET_FIELDS or (path.endswith(".auth") and lowered == "value"):
                raise ConfigError(f"plaintext secret field is not allowed: {path}.{key}".strip("."))
            _reject_plaintext_secrets(item, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_plaintext_secrets(item, f"{path}.{index}")


def _capabilities(kind: str) -> dict[str, Any]:
    caps = {
        "tools": kind in {"openai", "openai-compatible", "openrouter", "kimi", "vllm", "sglang"},
        "streaming": kind != "ollama",
        "structured_outputs": kind in {"openai", "openai-compatible", "openrouter", "kimi", "vllm", "sglang"},
        "web": kind in {"openai", "openrouter"},
        "cache": kind in {"openai", "vllm", "sglang"},
        "offline_safe": kind in LOCAL_KINDS,
    }
    if kind == "kimi":
        caps["max_context_tokens"] = 256000
        caps["reasoning"] = "required"
    return caps


def _discover_models(profile: dict[str, Any], *, opener: Any | None = None) -> dict[str, Any]:
    kind = str(profile.get("kind") or "")
    base_url = str(profile.get("base_url") or "").rstrip("/")
    opener = opener or urllib.request.urlopen
    if kind == "ollama":
        url = f"{base_url or 'http://localhost:11434'}/api/tags"
    elif kind in COMPATIBLE_KINDS | {"openai"}:
        url = f"{_api_base(base_url, kind)}/models"
    else:
        return {"status": "not_supported", "models": []}
    try:
        request = urllib.request.Request(url, headers=_auth_headers(profile))
        with opener(request, timeout=5) as response:
            payload = json.loads(response.read().decode())
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"status": "unreachable", "models": [], "error": str(exc)}
    models = _models_from_payload(kind, payload)
    return {"status": "ok", "models": models}


def _models_from_payload(kind: str, payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    if kind == "ollama":
        raw = payload.get("models")
        return [str(item.get("name") or item.get("model")) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    raw = payload.get("data")
    return [str(item.get("id")) for item in raw if isinstance(item, dict) and item.get("id")] if isinstance(raw, list) else []


def _auth_headers(profile: dict[str, Any]) -> dict[str, str]:
    auth = profile.get("auth")
    if not isinstance(auth, dict) or not auth.get("env"):
        return {}
    value = os.environ.get(str(auth["env"]))
    return {"Authorization": f"Bearer {value}"} if value else {}


def _api_base(base_url: str, kind: str) -> str:
    if base_url:
        return base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    if kind == "openai":
        return "https://api.openai.com/v1"
    if kind == "openrouter":
        return "https://openrouter.ai/api/v1"
    if kind == "kimi":
        return "https://api.moonshot.ai/v1"
    return base_url


def _first_profile(providers: dict[str, Any]) -> str:
    return sorted(providers)[0] if providers else ""


def _first_profile_where(providers: dict[str, Any], predicate: Any) -> str:
    for profile_id in sorted(providers):
        if predicate(providers[profile_id]):
            return profile_id
    return ""


def _rate_limited(profile: Any) -> bool:
    limits = profile.get("limits") if isinstance(profile, dict) else {}
    if not isinstance(limits, dict):
        return False
    return limits.get("max_concurrent_requests") == 0 or limits.get("requests_per_minute") == 0


def _has_capability(profile: Any, capability: str) -> bool:
    caps = profile.get("capabilities") if isinstance(profile, dict) else {}
    return bool(caps.get(capability)) if isinstance(caps, dict) else False


def _host(url: str) -> str:
    return url.split("//", 1)[-1].split("/", 1)[0] if url else ""


def _write_section(lines: list[str], section: str, values: dict[str, Any]) -> None:
    simple = {key: value for key, value in values.items() if not isinstance(value, dict)}
    if simple:
        lines.append("")
        lines.append(f"[{section}]")
        for key, value in sorted(simple.items()):
            lines.append(f"{key} = {_toml_value(value)}")
    for key, value in sorted(values.items()):
        if isinstance(value, dict):
            lines.append("")
            lines.append(f"[{section}.{key}]")
            for child_key, child in sorted(value.items()):
                lines.append(f"{child_key} = {_toml_value(child)}")


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {_toml_value(item)}" for key, item in sorted(value.items())) + " }"
    return json.dumps(str(value))
