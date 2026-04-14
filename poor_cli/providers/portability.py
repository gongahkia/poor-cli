"""Harness portability enforcement (MH9).

Provider adapters call ``enforce_portability(provider, feature, config)`` before
using any stateful-API code path (e.g. OpenAI Responses API with ``store=True``,
Anthropic Managed Agents, server-side cross-session memory). When
``config.providers_portability.strict`` is True, these calls raise
``PortabilityViolation`` unless the feature has been explicitly opted into via
``allowed_stateful_features``.

The goal is the anti-Codex-lock-in stance from the open-harness thesis:
if you can't reconstruct a session from ~/.poor-cli/ alone, that state is not
portable. This gate prevents provider adapters from silently binding your
session to a closed server-side store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..config import Config

# known non-portable features. Anything a provider adapter does that relies on
# server-side state must use one of these codes (or add a new one here + in
# docs/HARNESS_PORTABILITY.md).
STATEFUL_FEATURES = {
    "openai_responses_stateful": (
        "OpenAI Responses API with store=True or previous_response_id. "
        "State lives on OpenAI's servers and is not reconstructible from local "
        "history alone."
    ),
    "anthropic_managed_agents": (
        "Anthropic Managed Agents / server-side session IDs. "
        "Session state is opaque; swapping providers mid-session drops context."
    ),
    "codex_encrypted_compaction": (
        "Codex-style encrypted compaction summary that cannot be decoded "
        "outside the originating provider."
    ),
    "provider_side_memory": (
        "Any provider-side long-term memory store that does not dump to local "
        "files under ~/.poor-cli/."
    ),
}


class PortabilityViolation(RuntimeError):
    """Raised when a provider tries to use a stateful API that is not allowed.

    The exception message includes the provider name, the feature code, and a
    user-facing remediation hint (flip ``providers_portability.strict=false``
    or add the feature to ``allowed_stateful_features``).
    """


def enforce_portability(
    provider: str,
    feature: str,
    config: Optional["Config"] = None,
) -> None:
    """Raise PortabilityViolation if strict mode blocks the feature.

    No-op when config is None (during bootstrap / tests without a Config) or
    when ``providers_portability.strict`` is False.
    """
    if config is None:
        return
    policy = getattr(config, "providers_portability", None)
    if policy is None or not getattr(policy, "strict", False):
        return
    allowed = (policy.allowed_stateful_features or {}).get(provider, []) or []
    if feature in allowed:
        return
    description = STATEFUL_FEATURES.get(feature, feature)
    raise PortabilityViolation(
        f"[{provider}] stateful-API feature '{feature}' is blocked by "
        f"providers_portability.strict=True. {description} "
        f"To allow it explicitly: add '{feature}' to "
        f"providers_portability.allowed_stateful_features['{provider}'] in "
        f"your config, or set providers_portability.strict=false to disable "
        f"the gate globally."
    )


def is_strict(config: Optional["Config"]) -> bool:
    """Return True when the portability gate is active."""
    if config is None:
        return False
    policy = getattr(config, "providers_portability", None)
    return bool(policy and getattr(policy, "strict", False))
