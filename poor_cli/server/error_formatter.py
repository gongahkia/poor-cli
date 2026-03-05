"""Error formatting utilities for JSON-RPC error responses."""

import ast
import json
from typing import Any, Dict, List, Optional, Tuple

_MAX_ERROR_MESSAGE_LEN = 360


def _collapse_whitespace(text: str) -> str:
    """Normalize all whitespace runs to a single space."""
    return " ".join(text.split())


def _try_parse_mapping(text: str) -> Optional[Dict[str, Any]]:
    """Try parsing a string into a dictionary via JSON or Python literal syntax."""
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_reason(details: Any) -> Optional[str]:
    """Extract a provider reason code from nested details blocks, if present."""
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict):
                reason = item.get("reason")
                if isinstance(reason, str) and reason.strip():
                    return _collapse_whitespace(reason)
                nested = _extract_reason(item.get("details"))
                if nested:
                    return nested
    return None


def _extract_structured_error_fields(
    payload: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract normalized message, reason, and status fields from structured API payloads."""
    message: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None

    error_obj = payload.get("error")
    if isinstance(error_obj, dict):
        value = error_obj.get("message")
        if isinstance(value, str) and value.strip():
            message = _collapse_whitespace(value)

        value = error_obj.get("status")
        if isinstance(value, str) and value.strip():
            status = _collapse_whitespace(value)

        reason = _extract_reason(error_obj.get("details"))

    payload_message = payload.get("message")
    if isinstance(payload_message, str) and payload_message.strip():
        nested_payload = _try_parse_mapping(payload_message.strip())
        if nested_payload is not None:
            nested_message, nested_reason, nested_status = _extract_structured_error_fields(
                nested_payload
            )
            message = message or nested_message
            reason = reason or nested_reason
            status = status or nested_status
        elif message is None:
            message = _collapse_whitespace(payload_message)

    payload_status = payload.get("status")
    if status is None and isinstance(payload_status, str) and payload_status.strip():
        status = _collapse_whitespace(payload_status)

    return message, reason, status


def _extract_structured_payload(raw: str) -> Optional[Dict[str, Any]]:
    """Find and parse an embedded dict/JSON payload inside a verbose exception string."""
    index = raw.find("{")
    while index != -1:
        candidate = raw[index:].strip()
        parsed = _try_parse_mapping(candidate)
        if parsed is not None:
            return parsed
        index = raw.find("{", index + 1)
    return None


def _trim_embedded_payload(compact: str) -> str:
    """Drop common serialized error blob suffixes from a compacted error string."""
    for marker in (" {'message':", ' {"message":', " {'error':", ' {"error":'):
        marker_index = compact.find(marker)
        if marker_index != -1:
            return compact[:marker_index].strip()
    return compact


def _sanitize_exception_message(error: Exception) -> str:
    """Build a concise, user-facing exception message for JSON-RPC responses."""
    raw = str(error).strip()
    if not raw:
        return error.__class__.__name__

    compact = _collapse_whitespace(raw.replace("\\n", " ").replace("\\t", " "))
    message = _trim_embedded_payload(compact)

    payload = _extract_structured_payload(raw)
    if payload is not None:
        extracted_message, extracted_reason, extracted_status = _extract_structured_error_fields(
            payload
        )

        detail_parts: List[str] = []
        if extracted_message:
            detail_parts.append(extracted_message)
        if extracted_reason:
            detail_parts.append(f"({extracted_reason})")
        elif extracted_status:
            detail_parts.append(f"({extracted_status})")

        detail = " ".join(detail_parts).strip()
        if detail and detail.lower() not in message.lower():
            message = f"{message}: {detail}" if message else detail

    if len(message) > _MAX_ERROR_MESSAGE_LEN:
        message = f"{message[:_MAX_ERROR_MESSAGE_LEN - 3].rstrip()}..."
    return message
