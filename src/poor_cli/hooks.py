from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib.metadata import entry_points
from typing import Any, Protocol


class Hook(Protocol):
    def before_turn(self, context: Mapping[str, Any]) -> None: ...

    def after_tool_call(self, context: Mapping[str, Any], result: Any) -> None: ...

    def before_model_call(self, context: Mapping[str, Any]) -> None: ...

    def after_run(self, context: Mapping[str, Any]) -> None: ...


class BaseHook:
    def before_turn(self, context: Mapping[str, Any]) -> None:
        pass

    def after_tool_call(self, context: Mapping[str, Any], result: Any) -> None:
        pass

    def before_model_call(self, context: Mapping[str, Any]) -> None:
        pass

    def after_run(self, context: Mapping[str, Any]) -> None:
        pass


class HookLoadError(RuntimeError):
    pass


class HookManager:
    def __init__(self, hooks: Iterable[Hook] = ()):
        self.hooks = list(hooks)

    @classmethod
    def from_hooks(cls, hooks: Iterable[Hook] | Hook | None = None) -> HookManager:
        if hooks is None:
            return cls()
        if isinstance(hooks, Iterable):
            return cls(hooks)
        return cls([hooks])

    def before_turn(self, context: Mapping[str, Any]) -> None:
        for hook in self.hooks:
            hook.before_turn(context)

    def after_tool_call(self, context: Mapping[str, Any], result: Any) -> None:
        for hook in self.hooks:
            hook.after_tool_call(context, result)

    def before_model_call(self, context: Mapping[str, Any]) -> None:
        for hook in self.hooks:
            hook.before_model_call(context)

    def after_run(self, context: Mapping[str, Any]) -> None:
        for hook in self.hooks:
            hook.after_run(context)


def load_hooks(group: str = "poor_cli.hooks") -> HookManager:
    loaded: list[Hook] = []
    selected = entry_points().select(group=group)
    for entry_point in selected:
        try:
            value = entry_point.load()
            loaded.append(value() if isinstance(value, type) else value)
        except Exception as exc:
            raise HookLoadError(f"failed to load hook {entry_point.name}: {exc}") from exc
    return HookManager(loaded)
