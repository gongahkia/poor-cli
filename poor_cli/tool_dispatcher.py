"""Phase-C hardened dispatcher for Phase-B tools.

Wraps the ``poor_cli.tools._registry`` table with:

- T1 strict JSONSchema validation before handler call
- T4 per-tool timeout + partial-result preservation
- T5 retry-with-backoff on TransientError
- T2 parallel dispatch of non-exclusive tools (via ``dispatch_many``)
- T8 per-tool cost attribution (wall time + any token costs the handler stamped)
- T10 ctx.call_tool helper for sub-tool invocation (depth-limited)

The legacy ``core_tool_dispatch`` stays in charge of the original
``read_file``, ``bash``, etc. tool surface. This module is the new entry
point for Phase-B and future tools; the two coexist during the migration.

Unit-testable in isolation: you can call ``dispatch_one`` with a fabricated
``SimpleNamespace`` ctx and a tool name; the registry state is shared with
the Phase-B registry so registrations in poor_cli.tools propagate
automatically.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from poor_cli.tool_blocks import TextBlock, ToolResult, wrap_legacy_result
from poor_cli.tool_errors import (
    PermissionDenied,
    SchemaValidationError,
    ToolError,
    TransientError,
)
from poor_cli.tools._registry import ToolSpec, get as registry_get


logger = logging.getLogger(__name__)

_MAX_CALL_DEPTH = 3  # T10 recursion limit


@dataclass
class RetryPolicy:
    """Per-tool retry configuration (T5). Default is 'no retry'."""
    max_attempts: int = 1
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0
    jitter: float = 0.25  # fraction of base_delay added/subtracted
    retry_on: Tuple[type, ...] = (TransientError,)


DEFAULT_RETRY_POLICY = RetryPolicy(max_attempts=1)
TRANSIENT_RETRY_POLICY = RetryPolicy(max_attempts=3, base_delay_s=0.5)


@dataclass
class CallRecord:
    """Per-call trace (T8). Accumulated per session by the caller."""
    tool: str
    wall_time_ms: int
    returncode: int
    tokens_in: int = 0
    tokens_out: int = 0
    retry_attempts: int = 0
    degraded: Optional[str] = None
    timeout: bool = False
    is_error: bool = False


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _validate_args(spec: ToolSpec, args: Dict[str, Any]) -> Optional[ToolResult]:
    """T1: run jsonschema against the tool's schema. Returns None on success,
    or a structured error ToolResult on validation failure."""
    schema = spec.schema
    if not schema:
        return None
    try:
        import jsonschema  # lazy: keep import cost off the cold path
        from jsonschema import Draft202012Validator
    except ImportError:
        # jsonschema is a pyproject dep; a missing install is a developer
        # environment problem, not a tool failure. Surface it once via the
        # logger and continue without validation.
        logger.warning("jsonschema not installed; skipping args validation")
        return None
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(args or {}), key=lambda e: list(e.path))
    if not errors:
        return None
    # The model sees one consolidated repair message. Include path + rule so
    # the model has enough to self-correct without having to guess.
    first = errors[0]
    path = "/".join(str(p) for p in first.path) or "<root>"
    msg = (
        f"Argument validation failed for tool {spec.name!r}:\n"
        f"  path: {path}\n"
        f"  error: {first.message}\n"
        f"  rule: {first.validator}={first.validator_value!r}\n"
        f"Please re-invoke with corrected args."
    )
    return ToolResult(
        content=[TextBlock(text=msg)],
        is_error=True,
        metadata={
            "validation_error": True,
            "path": path,
            "rule": first.validator,
        },
    )


async def _run_with_timeout(spec: ToolSpec, coro: Awaitable[Any]) -> Tuple[Any, bool]:
    """T4: race the handler against spec.timeout_s. Returns (result, timed_out)."""
    try:
        result = await asyncio.wait_for(coro, timeout=spec.timeout_s)
        return result, False
    except asyncio.TimeoutError:
        return None, True


async def _notify(ctx: Any, method: str, params: Dict[str, Any]) -> None:
    fn = getattr(ctx, "notify_client", None)
    if fn is None:
        return
    try:
        maybe = fn(method, params)
        if asyncio.iscoroutine(maybe):
            await maybe
    except Exception:
        pass


def _block_to_dict(block: Any) -> Dict[str, Any]:
    if hasattr(block, "to_dict"):
        return block.to_dict()
    return {"kind": "text", "text": str(block)}


def _normalize_chunks(chunks: List[Any]) -> List[Any]:
    out: List[Any] = []
    for c in chunks:
        if hasattr(c, "to_dict"):
            out.append(c)
        elif isinstance(c, str):
            out.append(TextBlock(text=c))
        else:
            out.append(TextBlock(text=str(c)))
    return out


async def _consume_stream(
    spec: ToolSpec, ctx: Any, generator: Any
) -> Tuple[ToolResult, bool]:
    """T3: drain an async-generator tool handler. Each yield is a
    ContentBlock or a dict ``{"block": ..., "final": bool, "metadata": {}}``.
    Each chunk is emitted as a ``poor-cli/toolStream`` notification."""
    chunks: List[Any] = []
    metadata: Dict[str, Any] = {}
    is_error = False
    final_marker_seen = False
    chunk_index = 0
    deadline = time.monotonic() + spec.timeout_s

    async def _pump() -> None:
        nonlocal chunk_index, is_error, final_marker_seen, metadata
        async for item in generator:
            if isinstance(item, dict) and "block" in item:
                block = item["block"]
                chunks.append(block)
                final_marker_seen = final_marker_seen or bool(item.get("final"))
                if item.get("metadata"):
                    metadata.update(item["metadata"])
                if item.get("is_error"):
                    is_error = True
            elif isinstance(item, ToolResult):
                chunks.extend(item.content)
                metadata.update(item.metadata or {})
                if item.is_error:
                    is_error = True
                final_marker_seen = True
            else:
                chunks.append(item)
            await _notify(
                ctx,
                "poor-cli/toolStream",
                {
                    "tool": spec.name,
                    "chunkIndex": chunk_index,
                    "chunk": _block_to_dict(chunks[-1]),
                    "final": final_marker_seen,
                },
            )
            chunk_index += 1

    try:
        remaining = max(0.001, deadline - time.monotonic())
        await asyncio.wait_for(_pump(), timeout=remaining)
    except asyncio.TimeoutError:
        metadata.update({"timeout": True, "timeout_s": spec.timeout_s})
        chunks.append(
            TextBlock(
                text=f"[tool {spec.name!r} timed out after {spec.timeout_s}s; partial result above]"
            )
        )
        return (
            ToolResult(content=_normalize_chunks(chunks), is_error=True, metadata=metadata),
            True,
        )
    if not chunks:
        chunks.append(TextBlock(text="(tool produced no output)"))
    return (
        ToolResult(content=_normalize_chunks(chunks), is_error=is_error, metadata=metadata),
        False,
    )


async def _dispatch_once(spec: ToolSpec, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    """Single attempt. Validates args, calls the handler, handles timeout +
    handler exceptions. Does NOT retry — that's ``_dispatch_with_retry``."""
    bad = _validate_args(spec, args)
    if bad is not None:
        return bad
    try:
        returned = spec.handler(ctx=ctx, args=args)
        if inspect.isasyncgen(returned):
            result, _timed_out = await _consume_stream(spec, ctx, returned)
            return result
        value, timed_out = await _run_with_timeout(spec, returned)
    except PermissionDenied as e:
        return ToolResult.error(str(e), permission_denied=True, **e.metadata)
    except TransientError:
        raise  # caller's retry loop handles
    except ToolError as e:
        return ToolResult.error(str(e), **e.metadata)
    except Exception as e:  # noqa: BLE001 — dispatcher firewall
        logger.exception("tool %r raised unhandled exception", spec.name)
        return ToolResult.error(f"tool raised: {e!r}", handler_exception=True)
    if timed_out:
        return ToolResult(
            content=[TextBlock(text=f"tool {spec.name!r} timed out after {spec.timeout_s}s")],
            is_error=True,
            metadata={"timeout": True, "timeout_s": spec.timeout_s},
        )
    return wrap_legacy_result(value)


async def _dispatch_with_retry(
    spec: ToolSpec,
    ctx: Any,
    args: Dict[str, Any],
    policy: RetryPolicy,
) -> Tuple[ToolResult, int]:
    """T5: exponential backoff + jitter on TransientError. Returns (result, attempts)."""
    attempts = 0
    last_transient: Optional[Exception] = None
    while attempts < max(1, policy.max_attempts):
        attempts += 1
        try:
            result = await _dispatch_once(spec, ctx, args)
            return result, attempts
        except TransientError as e:
            last_transient = e
            if attempts >= policy.max_attempts:
                break
            delay = min(
                policy.max_delay_s,
                policy.base_delay_s * (2 ** (attempts - 1)),
            )
            jitter = delay * policy.jitter
            delay = delay + random.uniform(-jitter, jitter)
            await asyncio.sleep(max(0.0, delay))
    # Exhausted retries on TransientError
    msg = f"tool {spec.name!r} failed after {attempts} attempt(s)"
    if last_transient is not None:
        msg += f": {last_transient!r}"
    return (
        ToolResult.error(msg, retry_exhausted=True, retry_attempts=attempts),
        attempts,
    )


async def dispatch_one(
    name: str,
    args: Dict[str, Any],
    *,
    ctx: Any,
    policy: Optional[RetryPolicy] = None,
    _depth: int = 0,
) -> Tuple[ToolResult, CallRecord]:
    """Dispatch a single tool call. Primary Phase-C entry point.

    Returns the ``ToolResult`` plus a ``CallRecord`` with cost attribution
    (T8) the caller can aggregate per-session.
    """
    spec = registry_get(name)
    if spec is None:
        rec = CallRecord(tool=name, wall_time_ms=0, returncode=1, is_error=True)
        return ToolResult.error(f"unknown tool: {name}", unknown_tool=True), rec
    if _depth >= _MAX_CALL_DEPTH:
        rec = CallRecord(tool=name, wall_time_ms=0, returncode=1, is_error=True)
        return (
            ToolResult.error(
                f"tool composition depth limit ({_MAX_CALL_DEPTH}) exceeded at {name!r}",
                depth_exhausted=True,
            ),
            rec,
        )
    # Proposal E.1 — memoization cache lookup. Only cacheable (non-exclusive)
    # tools participate. Cache hit returns verbatim with metadata.cache_hit.
    cache = getattr(ctx, "tool_cache", None)
    if spec.cacheable and cache is not None:
        hit = cache.get(name, args, ttl_s=spec.cache_ttl_s)
        if hit is not None:
            # Clone the metadata so we can stamp cache_hit without mutating
            # the shared cached instance (which would break subsequent hits).
            result = ToolResult(
                content=list(hit.content),
                is_error=hit.is_error,
                metadata={
                    **(hit.metadata or {}),
                    "cache_hit": True,
                    "wall_time_ms": 0,
                },
            )
            rec = CallRecord(
                tool=name,
                wall_time_ms=0,
                returncode=1 if result.is_error else 0,
                retry_attempts=0,
                is_error=result.is_error,
            )
            # Still record into SessionRecorder so meta.call_history shows
            # cache-hit calls for observability.
            recorder = getattr(ctx, "session_recorder", None)
            if recorder is not None:
                try:
                    recorder.record(rec, args)
                except Exception:
                    logger.debug("session_recorder.record raised", exc_info=True)
            return result, rec
    effective_policy = policy or DEFAULT_RETRY_POLICY
    t0 = _now_ms()
    # T10: expose a bound call_tool on ctx so handlers can invoke peers
    # without respawning sub-agents. We splice it in non-destructively.
    bound_ctx = _augment_ctx(ctx, _depth)
    result, attempts = await _dispatch_with_retry(spec, bound_ctx, args, effective_policy)
    wall = _now_ms() - t0
    meta = result.metadata or {}
    rec = CallRecord(
        tool=name,
        wall_time_ms=wall,
        returncode=1 if result.is_error else 0,
        tokens_in=int((meta.get("token_cost") or {}).get("in", 0) or 0),
        tokens_out=int((meta.get("token_cost") or {}).get("out", 0) or 0),
        retry_attempts=attempts,
        degraded=meta.get("degraded"),
        timeout=bool(meta.get("timeout")),
        is_error=result.is_error,
    )
    # Stamp wall_time_ms + retry_attempts into the returned metadata so
    # downstream renderers (timeline, cost dashboard) see them.
    result.metadata = {
        **(result.metadata or {}),
        "wall_time_ms": wall,
        "retry_attempts": attempts,
    }
    # Proposal D: if the session attached a SessionRecorder to ctx, push
    # every dispatch into it so meta.call_history + meta.what_changed can
    # introspect the trace without the agent having to keep it in chat.
    # The recorder lives on the unwrapped base ctx; the augmented Bound
    # proxy forwards getattr, so a naive lookup works.
    recorder = getattr(ctx, "session_recorder", None)
    if recorder is not None:
        try:
            recorder.record(rec, args)
        except Exception:
            logger.debug("session_recorder.record raised", exc_info=True)
    # Proposal E.1 — cache the (fresh) result + run invalidation chain.
    # We store only successful calls to avoid caching ToolErrors that might
    # recover on retry; validation/unknown-tool errors are short-circuited
    # earlier anyway.
    if cache is not None and spec.cacheable and not result.is_error:
        try:
            cache.put(name, args, result)
        except Exception:
            logger.debug("tool_cache.put raised", exc_info=True)
    if cache is not None and spec.invalidates and not result.is_error:
        try:
            cache.invalidate_many(spec.invalidates)
        except Exception:
            logger.debug("tool_cache.invalidate_many raised", exc_info=True)
    return result, rec


def _augment_ctx(ctx: Any, depth: int) -> Any:
    """Clone-with-call_tool for T10. Uses a thin proxy so callers see the
    original ctx's attributes plus a ``call_tool`` method scoped to depth+1."""
    if ctx is None:
        ctx = _EmptyCtx()
    if getattr(ctx, "_poor_cli_tool_ctx_depth", None) is not None:
        # already augmented at a previous depth; replace depth only
        ctx._poor_cli_tool_ctx_depth = depth
        return ctx

    class _Bound:
        def __init__(self, base: Any, d: int) -> None:
            object.__setattr__(self, "_base", base)
            object.__setattr__(self, "_poor_cli_tool_ctx_depth", d)

        def __getattr__(self, key: str) -> Any:
            return getattr(self._base, key)

        def __setattr__(self, key: str, value: Any) -> None:
            if key in {"_poor_cli_tool_ctx_depth", "_base"}:
                object.__setattr__(self, key, value)
                return
            setattr(self._base, key, value)

        async def call_tool(self, name: str, args: Dict[str, Any]) -> ToolResult:
            result, _rec = await dispatch_one(
                name, args, ctx=self._base, _depth=self._poor_cli_tool_ctx_depth + 1
            )
            return result

    return _Bound(ctx, depth)


class _EmptyCtx:
    def has_plugin(self, _name: str) -> bool:
        return False

    async def notify_client(self, _method: str, _params: Dict[str, Any]) -> None:
        return None


async def dispatch_many(
    calls: Sequence[Tuple[str, Dict[str, Any]]],
    *,
    ctx: Any,
    policy: Optional[RetryPolicy] = None,
) -> List[Tuple[ToolResult, CallRecord]]:
    """T2: parallel dispatch. Non-exclusive tools in ``calls`` run concurrently
    via ``asyncio.gather``. Exclusive tools (per their registration) serialize
    after all non-exclusive tools in the batch complete. Preserves input order
    in the returned list."""
    if not calls:
        return []
    non_exclusive: List[Tuple[int, str, Dict[str, Any]]] = []
    exclusive: List[Tuple[int, str, Dict[str, Any]]] = []
    for idx, (name, args) in enumerate(calls):
        spec = registry_get(name)
        if spec is not None and spec.exclusive:
            exclusive.append((idx, name, args))
        else:
            non_exclusive.append((idx, name, args))
    # Run non-exclusive concurrently
    async def _run(name: str, args: Dict[str, Any]) -> Tuple[ToolResult, CallRecord]:
        return await dispatch_one(name, args, ctx=ctx, policy=policy)

    results: Dict[int, Tuple[ToolResult, CallRecord]] = {}
    if non_exclusive:
        pairs = await asyncio.gather(*[_run(n, a) for _, n, a in non_exclusive])
        for (idx, _, _), pair in zip(non_exclusive, pairs):
            results[idx] = pair
    # Then exclusive, serially
    for idx, name, args in exclusive:
        results[idx] = await _run(name, args)
    return [results[i] for i in range(len(calls))]
