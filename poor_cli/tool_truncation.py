"""Dispatcher-side truncation pass (Proposal E.2).

Called from ``tool_dispatcher.dispatch_one`` after the handler returns a
``ToolResult``. If the rendered content exceeds ``max_result_tokens``
(per-tool override via ``ToolSpec.max_result_tokens`` or the default),
stash the full content in ``ctx.tool_blob_store`` and replace with a
middle-out-truncated copy carrying ``metadata.truncated = True`` +
``metadata.result_id`` so the agent can fetch the full blob on demand.

Middle-out (keep-head + keep-tail) preserves the signal most useful to the
agent: start of output tells it *what happened*, end tells it *how it
finished*. The noisy middle goes to the blob store.
"""

from __future__ import annotations

from typing import Any, List, Optional

from poor_cli.tool_blob_store import SessionBlobStore
from poor_cli.tool_blocks import (
    CodeBlock,
    ContentBlock,
    TextBlock,
    ToolResult,
)


_CHARS_PER_TOKEN = 4  # coarse but stable estimate across English + code
DEFAULT_MAX_RESULT_TOKENS = 8000


def _block_char_count(block: ContentBlock) -> int:
    """Approximate char count for token budgeting. Tables render by row;
    code blocks by their raw text; etc."""
    try:
        d = block.to_dict()
    except Exception:
        return len(str(block))
    total = 0
    for value in d.values():
        if isinstance(value, str):
            total += len(value)
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, str):
                    total += len(v)
                elif isinstance(v, list):
                    for sv in v:
                        if isinstance(sv, str):
                            total += len(sv) + 2  # row separator
        # booleans, ints, etc. — negligible
    return total


def _tool_result_char_count(result: ToolResult) -> int:
    return sum(_block_char_count(b) for b in result.content)


def _truncate_codeblock_middle(block: CodeBlock, *, keep_head: int, keep_tail: int) -> CodeBlock:
    """For the single largest content type — a code block — do middle-out
    truncation at the character level. Insert a clear marker in place of
    the elided middle so the agent knows it happened."""
    code = block.code
    if len(code) <= keep_head + keep_tail:
        return block
    head = code[:keep_head]
    tail = code[-keep_tail:]
    elided = len(code) - keep_head - keep_tail
    sep = f"\n\n... [{elided} chars elided from middle; fetch full via tool_blob.get(result_id=<id>)] ...\n\n"
    return CodeBlock(language=block.language, code=head + sep + tail)


def _truncate_textblock_middle(block: TextBlock, *, keep_head: int, keep_tail: int) -> TextBlock:
    text = block.text
    if len(text) <= keep_head + keep_tail:
        return block
    head = text[:keep_head]
    tail = text[-keep_tail:]
    elided = len(text) - keep_head - keep_tail
    sep = f"\n\n... [{elided} chars elided; fetch full via tool_blob.get] ...\n\n"
    return TextBlock(text=head + sep + tail)


def maybe_truncate(
    result: ToolResult,
    *,
    ctx: Any,
    max_result_tokens: int = DEFAULT_MAX_RESULT_TOKENS,
) -> ToolResult:
    """If the result is under budget, return it as-is. Otherwise stash the
    full content in ctx.tool_blob_store and return a truncated copy. Safe
    to call when ctx has no blob store — in that case we truncate in
    place without stashing (no fetch path available, but still bounds
    context)."""
    char_budget = max(200, max_result_tokens * _CHARS_PER_TOKEN)
    total = _tool_result_char_count(result)
    if total <= char_budget:
        return result

    blob_store: Optional[SessionBlobStore] = getattr(ctx, "tool_blob_store", None)
    original_tokens = total // _CHARS_PER_TOKEN

    # Stash full content first so the result_id can reference it.
    result_id: Optional[str] = None
    if blob_store is not None:
        try:
            result_id = blob_store.put(
                list(result.content),
                original_token_estimate=original_tokens,
            )
        except Exception:
            result_id = None

    # Build truncated content. Simple strategy: for single-block results
    # (common: one big CodeBlock / TextBlock), middle-truncate it. For
    # multi-block results, we keep all non-oversized blocks intact and
    # truncate the largest one(s).
    new_content: List[ContentBlock] = []
    remaining = char_budget
    keep_unit = max(200, remaining // 3)  # head + tail each ≤ 1/3 budget

    # Sort indices so we truncate biggest first; but preserve original
    # positional order in the output.
    indexed = list(enumerate(result.content))
    sizes = [(i, _block_char_count(b)) for i, b in indexed]
    biggest_idx = max(sizes, key=lambda t: t[1])[0] if sizes else None

    for i, block in indexed:
        block_size = _block_char_count(block)
        if block_size <= remaining and i != biggest_idx:
            new_content.append(block)
            remaining -= block_size
            continue
        # Truncate this block. Only CodeBlock + TextBlock support middle
        # truncation cleanly; for others, replace with a placeholder.
        if isinstance(block, CodeBlock):
            truncated = _truncate_codeblock_middle(
                block, keep_head=keep_unit, keep_tail=keep_unit
            )
            new_content.append(truncated)
        elif isinstance(block, TextBlock):
            truncated = _truncate_textblock_middle(
                block, keep_head=keep_unit, keep_tail=keep_unit
            )
            new_content.append(truncated)
        else:
            # Fallback: replace with a description placeholder.
            new_content.append(
                TextBlock(text=f"[{type(block).__name__} elided: {block_size} chars]")
            )
        # We've spent ~2*keep_unit on this block; reduce remaining so later
        # blocks don't also balloon.
        remaining = max(0, remaining - 2 * keep_unit)

    # Final instruction block so the agent knows the mechanism.
    fetch_note = TextBlock(
        text=(
            f"[truncated: original ≈{original_tokens} tokens; "
            + (f"fetch full via tool_blob.get(result_id={result_id!r})"
               if result_id else "no blob store attached — full content is lost for this session")
            + "]"
        )
    )
    new_content.append(fetch_note)

    new_metadata = {
        **(result.metadata or {}),
        "truncated": True,
        "original_token_estimate": original_tokens,
    }
    if result_id:
        new_metadata["result_id"] = result_id
    return ToolResult(
        content=new_content,
        is_error=result.is_error,
        metadata=new_metadata,
    )
