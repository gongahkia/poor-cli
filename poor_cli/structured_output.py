"""Grammar-constrained / structured output support for provider layer.

Defines JSON schemas for structured responses (tool calls, edits, plan mode)
and per-provider format builders so each provider can use its native
structured-output API.  Includes fallback tracking metrics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Response types that can be grammar-constrained
# ---------------------------------------------------------------------------

class StructuredResponseType(Enum):
    TOOL_CALL = "tool_call"
    EDIT_BLOCK = "edit_block"
    PLAN = "plan"
    JSON_EDIT = "json_edit"


# ---------------------------------------------------------------------------
# JSON schemas for each structured response type
# ---------------------------------------------------------------------------

EDIT_BLOCK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "search": {"type": "string"},
                    "replace": {"type": "string"},
                },
                "required": ["file", "search", "replace"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["edits"],
    "additionalProperties": False,
}

PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "action": {"type": "string"},
                },
                "required": ["description"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["steps"],
    "additionalProperties": False,
}

JSON_EDIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["set", "delete", "append"]},
                    "path": {"type": "string"},
                    "value": {},  # any type
                },
                "required": ["op", "path"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["operations"],
    "additionalProperties": False,
}

_SCHEMAS: Dict[StructuredResponseType, Dict[str, Any]] = {
    StructuredResponseType.EDIT_BLOCK: EDIT_BLOCK_SCHEMA,
    StructuredResponseType.PLAN: PLAN_SCHEMA,
    StructuredResponseType.JSON_EDIT: JSON_EDIT_SCHEMA,
}


def get_schema(response_type: StructuredResponseType) -> Optional[Dict[str, Any]]:
    """Return the JSON schema for a structured response type, or None."""
    return _SCHEMAS.get(response_type)


# ---------------------------------------------------------------------------
# Structured output config passed to providers
# ---------------------------------------------------------------------------

@dataclass
class StructuredOutputConfig:
    """Passed alongside a send_message call to request structured output."""
    response_type: StructuredResponseType
    schema: Dict[str, Any] = field(default_factory=dict)
    schema_name: str = ""  # human-readable name for the schema

    def __post_init__(self):
        if not self.schema:
            self.schema = get_schema(self.response_type) or {}
        if not self.schema_name:
            self.schema_name = self.response_type.value


# ---------------------------------------------------------------------------
# Per-provider response_format builders
# ---------------------------------------------------------------------------

def build_openai_response_format(config: StructuredOutputConfig) -> Dict[str, Any]:
    """Build OpenAI-style response_format with json_schema."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": config.schema_name,
            "strict": True,
            "schema": config.schema,
        },
    }


def build_gemini_response_schema(config: StructuredOutputConfig) -> Dict[str, Any]:
    """Return schema dict suitable for Gemini response_schema param."""
    return config.schema


def build_ollama_format(config: StructuredOutputConfig) -> str:
    """Ollama uses format: 'json' for basic JSON constraint."""
    return "json"


# ---------------------------------------------------------------------------
# Fallback & retry metrics
# ---------------------------------------------------------------------------

@dataclass
class StructuredOutputMetrics:
    """Tracks structured output attempts, successes, and fallbacks."""
    total_requests: int = 0
    structured_requests: int = 0
    structured_successes: int = 0
    fallback_to_unstructured: int = 0
    parse_failures_before: int = 0  # pre-structured-output baseline
    parse_failures_after: int = 0   # post-structured-output
    _start_time: float = field(default_factory=time.monotonic)

    def record_structured_attempt(self, success: bool) -> None:
        self.total_requests += 1
        self.structured_requests += 1
        if success:
            self.structured_successes += 1
        else:
            self.fallback_to_unstructured += 1

    def record_unstructured(self) -> None:
        self.total_requests += 1

    def record_parse_failure(self, *, structured: bool) -> None:
        if structured:
            self.parse_failures_after += 1
        else:
            self.parse_failures_before += 1

    @property
    def structured_success_rate(self) -> float:
        if self.structured_requests == 0:
            return 0.0
        return self.structured_successes / self.structured_requests

    @property
    def fallback_rate(self) -> float:
        if self.structured_requests == 0:
            return 0.0
        return self.fallback_to_unstructured / self.structured_requests

    def summary(self) -> Dict[str, Any]:
        elapsed = time.monotonic() - self._start_time
        return {
            "total_requests": self.total_requests,
            "structured_requests": self.structured_requests,
            "structured_successes": self.structured_successes,
            "fallback_to_unstructured": self.fallback_to_unstructured,
            "structured_success_rate": round(self.structured_success_rate, 4),
            "fallback_rate": round(self.fallback_rate, 4),
            "parse_failures_before": self.parse_failures_before,
            "parse_failures_after": self.parse_failures_after,
            "elapsed_seconds": round(elapsed, 1),
        }


# module-level singleton for session-wide tracking
_metrics = StructuredOutputMetrics()


def get_metrics() -> StructuredOutputMetrics:
    return _metrics


def reset_metrics() -> None:
    global _metrics
    _metrics = StructuredOutputMetrics()


# ---------------------------------------------------------------------------
# Helper: should this request use structured output?
# ---------------------------------------------------------------------------

def should_use_structured_output(
    *,
    provider_name: str,
    supports_structured: bool,
    response_type: Optional[StructuredResponseType],
) -> bool:
    """Determine if a request should use grammar-constrained output.

    Returns False for free-form text responses or providers that don't support it.
    """
    if response_type is None:
        return False
    if not supports_structured:
        return False
    if response_type == StructuredResponseType.TOOL_CALL:
        return False  # tool calls use native function calling, not response_format
    return True
