from __future__ import annotations

from typing import Any, Awaitable, Callable

Handler = Callable[[Any, dict[str, Any]], Awaitable[Any]]
REGISTRY: dict[str, Handler] = {}


def register(method: str):
    def deco(fn: Handler) -> Handler:
        if method in REGISTRY:
            raise RuntimeError(f"duplicate rpc registration: {method}")
        REGISTRY[method] = fn
        return fn

    return deco


rpc = register
