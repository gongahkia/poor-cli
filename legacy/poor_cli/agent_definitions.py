"""Markdown-defined sub-agent discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

import yaml


AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
HARD_DENIED_TOOLS = frozenset({"delegate_task", "spawn_parallel_agents"})


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    system_prompt: str
    model: Optional[str] = None
    provider: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
    denied_tools: List[str] = field(default_factory=list)
    max_thinking_tokens: int = 4096
    max_output_tokens: int = 4096
    hooks: Dict[str, str] = field(default_factory=dict)
    source_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "systemPrompt": self.system_prompt,
            "model": self.model,
            "provider": self.provider,
            "allowedTools": list(self.allowed_tools) if self.allowed_tools is not None else None,
            "deniedTools": list(self.denied_tools),
            "maxThinkingTokens": self.max_thinking_tokens,
            "maxOutputTokens": self.max_output_tokens,
            "hooks": dict(self.hooks),
            "sourcePath": self.source_path,
        }


class AgentDefinitionRegistry:
    """Loads .poor-cli/agents/*.md and exposes them by name."""

    def __init__(self, repo_root: Path, available_tools: Optional[Sequence[str]] = None):
        self.repo_root = repo_root.resolve()
        self.agents_dir = self.repo_root / ".poor-cli" / "agents"
        self._available_tools = set(available_tools) if available_tools is not None else _registered_tool_names()
        self._defs: Dict[str, AgentDefinition] = {}
        self._errors: List[Dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        self._defs = {}
        self._errors = []
        if not self.agents_dir.is_dir():
            return
        for path in sorted(self.agents_dir.glob("*.md")):
            try:
                definition = self.parse(path)
                self._validate(definition, path)
            except Exception as exc:
                self._errors.append({"path": str(path), "error": str(exc)})
                continue
            self._defs[definition.name] = definition

    def get(self, name: str) -> Optional[AgentDefinition]:
        return self._defs.get(name)

    def list(self) -> List[AgentDefinition]:
        return [self._defs[name] for name in sorted(self._defs)]

    def errors(self) -> List[Dict[str, Any]]:
        return list(self._errors)

    @staticmethod
    def parse(path: Path) -> AgentDefinition:
        text = path.read_text(encoding="utf-8")
        metadata, body = _split_frontmatter(text)
        name = str(metadata.get("name") or path.stem).strip()
        budget = metadata.get("budget") if isinstance(metadata.get("budget"), dict) else {}
        hooks = metadata.get("hooks") if isinstance(metadata.get("hooks"), dict) else {}
        allowed_tools = _string_list_or_none(metadata.get("allowed_tools"))
        denied_tools = _string_list_or_none(metadata.get("denied_tools")) or []
        return AgentDefinition(
            name=name,
            description=str(metadata.get("description") or "").strip(),
            system_prompt=body.strip(),
            model=_optional_string(metadata.get("model")),
            provider=_optional_string(metadata.get("provider")),
            allowed_tools=allowed_tools,
            denied_tools=denied_tools,
            max_thinking_tokens=int(budget.get("max_thinking_tokens") or 4096),
            max_output_tokens=int(budget.get("max_output_tokens") or 4096),
            hooks={str(key): str(value) for key, value in hooks.items()},
            source_path=str(path),
        )

    def _validate(self, definition: AgentDefinition, path: Path) -> None:
        if not AGENT_NAME_RE.match(definition.name):
            raise ValueError(f"invalid agent name: {definition.name!r}")
        if definition.name != path.stem:
            raise ValueError(f"agent name {definition.name!r} must match filename stem {path.stem!r}")
        if not definition.system_prompt:
            raise ValueError("system prompt body is required")
        unknown = _unknown_tools(definition.allowed_tools or [], self._available_tools)
        unknown.extend(_unknown_tools(definition.denied_tools, self._available_tools))
        if unknown:
            raise ValueError(f"unknown tool(s): {', '.join(sorted(set(unknown)))}")


def effective_allowed_tools(definition: AgentDefinition, available_tools: Sequence[str]) -> Set[str]:
    allowed = set(definition.allowed_tools) if definition.allowed_tools is not None else set(available_tools)
    return (allowed - set(definition.denied_tools)) - set(HARD_DENIED_TOOLS)


def _split_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        raise ValueError("unterminated YAML frontmatter")
    raw = text[4:end]
    body = text[end + len(marker):]
    metadata = yaml.safe_load(raw) or {}
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a mapping")
    return metadata, body


def _string_list_or_none(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("tool lists must be YAML lists")
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_string(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _unknown_tools(tools: Sequence[str], available: Set[str]) -> List[str]:
    return [tool for tool in tools if tool not in available]


def _registered_tool_names() -> Set[str]:
    try:
        from .tools_async import ToolRegistryAsync
        return set(ToolRegistryAsync().tools.keys())
    except Exception:
        return set()
