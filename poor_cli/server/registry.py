from __future__ import annotations

import ast
import importlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Awaitable, Callable

Handler = Callable[[Any, dict[str, Any]], Awaitable[Any]]
REGISTRY: dict[str, Handler] = {}
_HANDLER_DIR = Path(__file__).resolve().parent / "handlers"
_HANDLER_PACKAGE = "poor_cli.server.handlers"
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
    "mcp",
)
_HANDLER_RANK = {name: idx for idx, name in enumerate(_HANDLER_ORDER)}
_REGISTER_DECORATORS = {"register", "rpc"}
_RPC_METHOD_TO_MODULE: dict[str, str] | None = None
_ATTR_TO_MODULE: dict[str, str] | None = None
_LOADED_MODULES: set[str] = set()
_REGISTRY_CACHE_VERSION = 1
_REGISTRY_STATIC_INDEX_VERSION = 1
_INDEX_SOURCE: str | None = None
_STATIC_INDEX_PATH = Path(__file__).resolve().with_name("registry_static_index.json")
_PERF_LOG = os.environ.get("POORCLI_SERVER_PERF_LOG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
logger = logging.getLogger(__name__)


def register(method: str):
    def deco(fn: Handler) -> Handler:
        if method in REGISTRY:
            raise RuntimeError(f"duplicate rpc registration: {method}")
        REGISTRY[method] = fn
        return fn

    return deco


rpc = register


def _module_rank(module_name: str) -> int:
    stem = module_name.rsplit(".", 1)[-1]
    return _HANDLER_RANK.get(stem, len(_HANDLER_RANK) + 100)


def _register_method_from_decorator(decorator: ast.AST) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Name):
        return None
    if decorator.func.id not in _REGISTER_DECORATORS:
        return None
    if not decorator.args:
        return None
    first_arg = decorator.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return first_arg.value
    return None


def _registry_cache_path() -> Path:
    raw = os.environ.get("POORCLI_SERVER_REGISTRY_CACHE_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".poor-cli" / "cache" / "server-registry-index-v1.json").resolve()


def _registry_static_index_path() -> Path:
    raw = os.environ.get("POORCLI_SERVER_REGISTRY_STATIC_INDEX_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _STATIC_INDEX_PATH


def _handler_signature() -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(_HANDLER_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append(
            {
                "name": path.name,
                "size": int(stat.st_size),
                "mtimeNs": int(stat.st_mtime_ns),
            }
        )
    return {
        "version": _REGISTRY_CACHE_VERSION,
        "handlerPackage": _HANDLER_PACKAGE,
        "handlerOrder": list(_HANDLER_ORDER),
        "files": files,
    }


def _parse_index_payload(payload: Any) -> tuple[dict[str, str], dict[str, str]] | None:
    if not isinstance(payload, dict):
        return None
    rpc_index = payload.get("rpcIndex")
    attr_index = payload.get("attrIndex")
    if not isinstance(rpc_index, dict) or not isinstance(attr_index, dict):
        return None
    try:
        rpc_clean = {str(key): str(value) for key, value in rpc_index.items()}
        attr_clean = {str(key): str(value) for key, value in attr_index.items()}
    except Exception:
        return None
    return rpc_clean, attr_clean


def _load_cached_indexes(signature: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]] | None:
    path = _registry_cache_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("signature") != signature:
        return None
    return _parse_index_payload(payload)


def _load_static_indexes() -> tuple[dict[str, str], dict[str, str]] | None:
    path = _registry_static_index_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("version", 0) or 0) != _REGISTRY_STATIC_INDEX_VERSION:
        return None
    if payload.get("handlerPackage") != _HANDLER_PACKAGE:
        return None
    if payload.get("handlerOrder") != list(_HANDLER_ORDER):
        return None
    return _parse_index_payload(payload)


def _store_cached_indexes(
    signature: dict[str, Any],
    rpc_index: dict[str, str],
    attr_index: dict[str, str],
) -> None:
    path = _registry_cache_path()
    payload = {
        "signature": signature,
        "rpcIndex": rpc_index,
        "attrIndex": attr_index,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    except Exception:
        return


def _scan_indexes_from_ast() -> tuple[dict[str, str], dict[str, str]]:
    rpc_index: dict[str, str] = {}
    attr_index: dict[str, str] = {}
    rpc_rank: dict[str, int] = {}
    attr_rank: dict[str, int] = {}

    for path in sorted(_HANDLER_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        module_name = f"{_HANDLER_PACKAGE}.{path.stem}"
        rank = _module_rank(module_name)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            logger.debug("handler index skip file=%s error=%s", path, exc)
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    method_name = _register_method_from_decorator(decorator)
                    if method_name is None:
                        continue
                    existing_rank = rpc_rank.get(method_name)
                    if existing_rank is None or rank < existing_rank:
                        rpc_index[method_name] = module_name
                        rpc_rank[method_name] = rank
                continue

            if not isinstance(node, ast.ClassDef) or not node.name.endswith("HandlersMixin"):
                continue
            for class_node in node.body:
                if not isinstance(class_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                attr_name = class_node.name
                existing_rank = attr_rank.get(attr_name)
                if existing_rank is None or rank < existing_rank:
                    attr_index[attr_name] = module_name
                    attr_rank[attr_name] = rank

    return rpc_index, attr_index


def _set_indexes(rpc_index: dict[str, str], attr_index: dict[str, str], *, source: str) -> None:
    global _RPC_METHOD_TO_MODULE, _ATTR_TO_MODULE, _INDEX_SOURCE
    _RPC_METHOD_TO_MODULE = rpc_index
    _ATTR_TO_MODULE = attr_index
    _INDEX_SOURCE = source


def _build_indexes() -> None:
    if _RPC_METHOD_TO_MODULE is not None and _ATTR_TO_MODULE is not None:
        return

    started = time.perf_counter()
    static = _load_static_indexes()
    if static is not None:
        rpc_index, attr_index = static
        _set_indexes(rpc_index, attr_index, source="static")
        if _PERF_LOG:
            logger.info(
                "perf registry_index_static_hit methods=%d attrs=%d elapsed_ms=%.2f",
                len(rpc_index),
                len(attr_index),
                (time.perf_counter() - started) * 1000.0,
            )
        return

    signature = _handler_signature()
    cached = _load_cached_indexes(signature)
    if cached is not None:
        rpc_index, attr_index = cached
        _set_indexes(rpc_index, attr_index, source="cache")
        if _PERF_LOG:
            logger.info(
                "perf registry_index_cache_hit methods=%d attrs=%d elapsed_ms=%.2f",
                len(rpc_index),
                len(attr_index),
                (time.perf_counter() - started) * 1000.0,
            )
        return

    rpc_index, attr_index = _scan_indexes_from_ast()
    _set_indexes(rpc_index, attr_index, source="ast")
    _store_cached_indexes(signature, rpc_index, attr_index)

    if _PERF_LOG:
        logger.info(
            "perf registry_index_build modules=%d methods=%d attrs=%d elapsed_ms=%.2f",
            len({value for value in rpc_index.values()}),
            len(rpc_index),
            len(attr_index),
            (time.perf_counter() - started) * 1000.0,
        )


def _rebuild_indexes_from_ast() -> None:
    started = time.perf_counter()
    signature = _handler_signature()
    rpc_index, attr_index = _scan_indexes_from_ast()
    _set_indexes(rpc_index, attr_index, source="ast")
    _store_cached_indexes(signature, rpc_index, attr_index)
    if _PERF_LOG:
        logger.info(
            "perf registry_index_ast_fallback methods=%d attrs=%d elapsed_ms=%.2f",
            len(rpc_index),
            len(attr_index),
            (time.perf_counter() - started) * 1000.0,
        )


def build_static_index_payload() -> dict[str, Any]:
    rpc_index, attr_index = _scan_indexes_from_ast()
    return {
        "version": _REGISTRY_STATIC_INDEX_VERSION,
        "handlerPackage": _HANDLER_PACKAGE,
        "handlerOrder": list(_HANDLER_ORDER),
        "rpcIndex": dict(sorted(rpc_index.items())),
        "attrIndex": dict(sorted(attr_index.items())),
    }


def write_static_index(path: Path | None = None) -> Path:
    out_path = (path or _registry_static_index_path()).expanduser().resolve()
    payload = build_static_index_payload()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def _import_handler_module(module_name: str) -> bool:
    if module_name in _LOADED_MODULES:
        return False

    started = time.perf_counter()
    module = importlib.import_module(module_name)
    from .handlers import graft_mixins_from_module

    graft_mixins_from_module(module_name.rsplit(".", 1)[-1], module)
    _LOADED_MODULES.add(module_name)

    if _PERF_LOG:
        logger.info(
            "perf handler_module_load module=%s registry_size=%d elapsed_ms=%.2f",
            module_name,
            len(REGISTRY),
            (time.perf_counter() - started) * 1000.0,
        )
    return True


def ensure_handler_for_method(method: str) -> bool:
    if method in REGISTRY:
        return False
    _build_indexes()
    module_name = (_RPC_METHOD_TO_MODULE or {}).get(method)
    if not module_name:
        return False
    _import_handler_module(module_name)
    if method in REGISTRY:
        return True
    if _INDEX_SOURCE == "static":
        _rebuild_indexes_from_ast()
        retry_module = (_RPC_METHOD_TO_MODULE or {}).get(method)
        if retry_module:
            _import_handler_module(retry_module)
    return method in REGISTRY


def ensure_handler_for_attr(attr_name: str) -> bool:
    _build_indexes()
    module_name = (_ATTR_TO_MODULE or {}).get(attr_name)
    if not module_name:
        return False
    loaded = _import_handler_module(module_name)
    from .handlers import HandlerMixin

    if hasattr(HandlerMixin, attr_name):
        return loaded
    if _INDEX_SOURCE == "static":
        _rebuild_indexes_from_ast()
        retry_module = (_ATTR_TO_MODULE or {}).get(attr_name)
        if retry_module:
            loaded = _import_handler_module(retry_module) or loaded
    return loaded


def ensure_handlers_loaded() -> int:
    _build_indexes()
    loaded = 0
    modules = sorted(
        set((_RPC_METHOD_TO_MODULE or {}).values()),
        key=lambda module: (_module_rank(module), module),
    )
    for module_name in modules:
        if _import_handler_module(module_name):
            loaded += 1
    return loaded
