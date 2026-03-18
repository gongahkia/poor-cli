"""Invite encoding helpers for owner-authoritative multiplayer."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


INVITE_VERSION = 1
INVITE_KIND = "poor-cli-p2p"


def _b64url_encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64url_decode_bytes(value: str) -> bytes:
    padded = value + ("=" * ((4 - (len(value) % 4)) % 4))
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def build_owner_fingerprint(secret: str) -> str:
    """Create a short stable owner fingerprint from the host secret."""
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return digest[:16]


def build_signed_invite(payload: Dict[str, Any], *, secret: str) -> str:
    """Return a versioned, signed invite code."""
    body = dict(payload)
    body["v"] = INVITE_VERSION
    body["kind"] = INVITE_KIND
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    signature = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    envelope = {
        "payload": body,
        "sig": _b64url_encode_bytes(signature),
    }
    return _b64url_encode_bytes(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def decode_invite_code(code: str) -> Dict[str, Any]:
    """Decode a signed invite or raise ValueError."""
    try:
        decoded = _b64url_decode_bytes(str(code or "").strip()).decode("utf-8")
        envelope = json.loads(decoded)
    except Exception as error:
        raise ValueError("invalid invite encoding") from error

    if not isinstance(envelope, dict):
        raise ValueError("invalid invite envelope")

    payload = envelope.get("payload")
    signature = envelope.get("sig")
    if not isinstance(payload, dict) or not isinstance(signature, str) or not signature:
        raise ValueError("invalid invite envelope")

    if int(payload.get("v", 0)) != INVITE_VERSION:
        raise ValueError("unsupported invite version")
    if str(payload.get("kind", "")) != INVITE_KIND:
        raise ValueError("invalid invite kind")

    return {
        "payload": payload,
        "sig": signature,
    }


def verify_signed_invite(
    code: str,
    *,
    secret: str,
    expected_session_id: Optional[str] = None,
    expected_role: Optional[str] = None,
) -> Dict[str, Any]:
    """Decode and validate a signed invite."""
    decoded = decode_invite_code(code)
    payload = dict(decoded["payload"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected_sig = _b64url_encode_bytes(
        hmac.new(
            secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(expected_sig, str(decoded["sig"])):
        raise ValueError("invalid invite signature")

    expires_at = str(payload.get("expiresAt", "")).strip()
    if expires_at:
        try:
            expires_dt = datetime.fromisoformat(expires_at)
        except ValueError as error:
            raise ValueError("invalid invite expiry") from error
        now = datetime.now(expires_dt.tzinfo or timezone.utc)
        if now >= expires_dt:
            raise ValueError("invite expired")

    if expected_session_id and str(payload.get("sessionId", "")) != expected_session_id:
        raise ValueError("invite session mismatch")
    if expected_role and str(payload.get("role", "")) != expected_role:
        raise ValueError("invite role mismatch")
    return payload
