# Harness Portability

poor-cli takes a hard stance on open-harness memory: if you can't reconstruct a session from `~/.poor-cli/` alone, that state is locked in. This document captures the stance, the enforcement mechanism, and the audit trail.

## Thesis

Agent harnesses are tightly coupled to agent memory. If your harness is closed or your provider's "memory" lives on their servers behind an opaque API, switching providers means losing accumulated context. Lock-in by design.

poor-cli's stance:
- Every conversation turn is stored as plain JSON under `~/.poor-cli/history.json` and `~/.poor-cli/sessions/`.
- Memories are plain markdown with YAML frontmatter under `~/.poor-cli/memory/*.md`.
- No provider adapter writes to a server-side state store that cannot be reconstructed from local files.
- Swapping providers mid-session replays local history to the new provider; nothing is lost.

## Enforcement

`poor_cli/providers/portability.py` exports:
- `Config.providers_portability.strict: bool = True` (default on).
- `enforce_portability(provider, feature, config)` — call before any stateful-API path.
- `PortabilityViolation` — raised when strict mode blocks a feature.
- `STATEFUL_FEATURES` — catalog of known non-portable feature codes.

Known non-portable feature codes:

| Code | Description |
|---|---|
| `openai_responses_stateful` | OpenAI Responses API with `store=True` or `previous_response_id`. State lives on OpenAI's servers; not reconstructible from local history. |
| `anthropic_managed_agents` | Anthropic Managed Agents / server-side session IDs. Session state is opaque; swapping providers mid-session drops context. |
| `codex_encrypted_compaction` | Codex-style encrypted compaction summary that cannot be decoded outside the originating provider. |
| `provider_side_memory` | Any provider-side long-term memory store that does not dump to local files under `~/.poor-cli/`. |

## Opt-in

A user who explicitly wants a stateful API (lower latency, specific features) can opt in per-provider:

```yaml
providers_portability:
  strict: true
  allowed_stateful_features:
    openai: ["openai_responses_stateful"]
```

Flipping `strict: false` disables the gate globally. Both paths carry a one-time warning so the user knows they've accepted lock-in.

## Regression Test

`tests/test_harness_portability.py` scans every provider adapter for:
1. Stateful-API call patterns (`store=True`, `previous_response_id=`, `managed_agent`, `assistant_id=`, `thread_id=`).
2. Persistent server-session attributes (`self._remote_session`, `self._server_session`, `self._stateful`).

Any such pattern must be guarded by a call to `enforce_portability(..., feature=<code>, ...)`. Unguarded patterns fail CI. New feature codes must be added to `STATEFUL_FEATURES` with a user-facing description.

## What's Safe

Prefix caching (Anthropic `cache_control`, OpenAI implicit) does not store session state — it caches prompt prefixes on the server for a short TTL. Safe.

KV-cache reuse via `kv_cache_store.py` is local-only (self-hosted vLLM/SGLang/HF TGI). Safe.

Semantic cache (`poor_cli/semantic_cache.py`) is local SQLite. Safe.

## What's Not Safe

Assistants API, Responses API with `store=True`, Anthropic Messages Batch with server-side result persistence, any "managed agent" or "hosted session" API. Not shipped; gated by `enforce_portability`.
