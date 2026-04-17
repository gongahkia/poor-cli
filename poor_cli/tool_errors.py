"""Error types for the Phase-C tool dispatcher.

Separate from the tool_blocks module so tools can raise these without
pulling in the full ToolResult machinery.
"""

from __future__ import annotations


class ToolError(Exception):
    """Non-transient tool failure. Dispatcher does not retry.

    Carries optional structured metadata that the dispatcher folds into the
    ToolResult.metadata so the model can reason over it.
    """

    def __init__(self, message: str, **metadata: object) -> None:
        super().__init__(message)
        self.metadata = metadata


class TransientError(Exception):
    """Transient tool failure. Dispatcher retries per RetryPolicy.

    Raise from inside a handler when the failure is a network blip, a 5xx
    from a provider, a filesystem EAGAIN, etc. — anything where retrying
    the identical call might succeed.
    """

    def __init__(self, message: str, **metadata: object) -> None:
        super().__init__(message)
        self.metadata = metadata


class PermissionDenied(ToolError):
    """Raised when the permission rule engine refuses a tool call. Not a
    transient — dispatcher short-circuits with an is_error ToolResult."""


class SchemaValidationError(ToolError):
    """Raised internally by the dispatcher when args fail jsonschema
    validation. Not meant to be raised by handler code."""
