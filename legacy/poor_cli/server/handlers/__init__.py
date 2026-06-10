from __future__ import annotations

from typing import Any

from poor_cli.server.registry import register, rpc
from .common import CommonHandlersMixin

_HANDLER_ORDER: tuple[str, ...] = (
    "common",
    "startup_state",
    "tools",
    "audit",
    "status",
    "chat",
    "chat_streaming",
    "config",
    "context",
    "providers",
    "sessions",
    "tasks",
    "tasks_async",
    "spec_handlers",
    "automations",
    "checkpoints",
    "services",
    "cost",
    "agents",
    "profiles",
    "trust",
    "memory",
    "deployment",
    "prompts",
    "misc",
    "diff_review",
    "timeline",
    "watch",
    "plan",
    "branches",
    "repo_map",
    "budget_hud",
    "mcp",
)
_HANDLER_RANK = {name: idx for idx, name in enumerate(_HANDLER_ORDER)}
_MEMBER_RANK: dict[str, int] = {}


class HandlerMixin(CommonHandlersMixin):
    def __getattr__(self, name: str) -> Any:
        from poor_cli.server.registry import ensure_handler_for_attr

        if ensure_handler_for_attr(name):
            try:
                return object.__getattribute__(self, name)
            except AttributeError:
                pass
        raise AttributeError(f"{self.__class__.__name__!r} object has no attribute {name!r}")


def _graft_mixin_class(mixin_cls: type[Any], rank: int) -> None:
    for name, value in mixin_cls.__dict__.items():
        if name in {"__module__", "__dict__", "__weakref__", "__doc__"}:
            continue
        existing_rank = _MEMBER_RANK.get(name)
        if existing_rank is not None and existing_rank <= rank:
            continue
        setattr(HandlerMixin, name, value)
        _MEMBER_RANK[name] = rank


def graft_mixins_from_module(module_name: str, module: Any) -> None:
    rank = _HANDLER_RANK.get(module_name, len(_HANDLER_RANK) + 100)
    for value in module.__dict__.values():
        if isinstance(value, type) and value.__name__.endswith("HandlersMixin"):
            _graft_mixin_class(value, rank)


_graft_mixin_class(CommonHandlersMixin, _HANDLER_RANK["common"])

__all__ = ["HandlerMixin", "graft_mixins_from_module", "register", "rpc"]
