"""Shared CLI error rendering for user-facing entrypoints."""

from __future__ import annotations

import re
from typing import Callable, Optional, TypeVar

from .exceptions import ConfigurationError, PoorCLIError
from .server.error_formatter import _sanitize_exception_message

_T = TypeVar("_T")
_API_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9_]*_API_KEY)\b")


def _configuration_hint(message: str) -> Optional[str]:
    api_key_match = _API_KEY_PATTERN.search(message)
    if api_key_match is not None:
        env_var = api_key_match.group(1)
        return f"Set `{env_var}` in the current shell, or rerun with `--api-key`."

    lowered = message.lower()
    if "no api key found for provider" in lowered:
        return "Set the provider API key in the current shell, or rerun with `--api-key`."
    return None


def format_cli_exception(error: BaseException) -> str:
    """Render a concise, user-facing error message for CLI entrypoints."""
    if isinstance(error, KeyboardInterrupt):
        return "Interrupted."

    if isinstance(error, Exception):
        message = _sanitize_exception_message(error)
    else:
        message = str(error).strip() or error.__class__.__name__

    hint: Optional[str] = None
    if isinstance(error, (ConfigurationError, PoorCLIError, RuntimeError)):
        hint = _configuration_hint(message)
    if hint:
        return f"{message}\n\n{hint}"
    return message


def run_with_cli_error_handling(callback: Callable[[], _T]) -> _T:
    """Execute a CLI entrypoint and convert expected failures into concise exits."""
    try:
        return callback()
    except SystemExit:
        raise
    except BaseException as error:
        raise SystemExit(format_cli_exception(error)) from None
