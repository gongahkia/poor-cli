"""tool_blob.get — retrieve a full (un-truncated) tool result by result_id.

Pairs with the truncation pass in ``poor_cli.tool_truncation``. When the
dispatcher trims an oversized result, it stashes the full content in the
session ``SessionBlobStore`` and surfaces a ``result_id`` in the
truncated result's metadata. The agent calls ``tool_blob.get({result_id})``
when it wants the full content.

Philosophical bearings:

- **Agent-centric.** The agent, not the user, decides when to spend
  tokens on the full blob. No UI; no user command.
- **Token-frugal.** The blob sits in-process until fetched. Calling
  this tool is the only way to pay for it.
- **Correctness over savings.** Truncated content still carries head +
  tail in the original result, so the agent almost never needs this for
  routine work — only when it's actively parsing a large artifact.
"""

from __future__ import annotations

from typing import Any, Dict

from poor_cli.tool_blocks import ToolResult
from poor_cli.tools._registry import register_tool


async def handle_get(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    result_id = args.get("result_id")
    if not isinstance(result_id, str) or not result_id:
        return ToolResult.error("result_id is required (string)")
    store = getattr(ctx, "tool_blob_store", None)
    if store is None:
        return ToolResult.error(
            "no blob store attached to this session — full content unavailable",
            unavailable=True,
        )
    entry = store.get(result_id)
    if entry is None:
        return ToolResult.error(
            f"unknown result_id {result_id!r} "
            "(blob may have been evicted by the session's cap_bytes policy)",
            unknown_result_id=True,
        )
    # Return the blocks verbatim. NOTE: we deliberately do NOT run this
    # result through the truncation pass again — the agent asked for it,
    # the agent accepts the token cost.
    return ToolResult(
        content=list(entry.content),
        is_error=False,
        metadata={
            "result_id": entry.result_id,
            "original_token_estimate": entry.original_token_estimate,
            "bypass_truncation": True,
        },
    )


register_tool(
    name="tool_blob.get",
    description=(
        "Retrieve the full (un-truncated) content of an earlier tool result "
        "by ``result_id``. Use when a prior tool call returned "
        "``metadata.truncated=True`` and you need the middle that was "
        "elided. The result bypasses the truncation budget — expect to "
        "spend tokens proportional to the original output."
    ),
    schema={
        "type": "object",
        "required": ["result_id"],
        "properties": {
            "result_id": {
                "type": "string",
                "pattern": "^blob_[0-9a-f]{8,16}$",
                "description": "result_id from a prior truncated ToolResult's metadata.",
            }
        },
        "additionalProperties": False,
    },
    handler=handle_get,
    examples=[
        {
            "when": "a git.diff was truncated but the elided hunks matter",
            "args": {"result_id": "blob_abc123"},
            "result_summary": "full CodeBlock as originally returned",
        }
    ],
    # Not cacheable: the blob store IS the cache; double-caching would
    # leak memory and not save any work.
    cacheable=False,
    # Very large budget override: by definition the agent called this to
    # GET the big blob, so the dispatcher shouldn't re-truncate it.
    max_result_tokens=1_000_000,
)
