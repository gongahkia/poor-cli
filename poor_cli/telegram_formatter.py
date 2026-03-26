"""format CoreEvent streams into Telegram-friendly messages."""

import re
from typing import List

TELEGRAM_MSG_LIMIT = 4096


def escape_markdown_v2(text: str) -> str:
    """escape special chars for Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special)}])", r"\\\1", text)


def format_tool_call(name: str, args: dict) -> str:
    """format a tool call as a compact Telegram message block."""
    arg_str = ", ".join(f"{k}={_truncate(str(v), 80)}" for k, v in args.items())
    return f"🔧 `{name}({arg_str})`"


def format_tool_result(name: str, result: str, success: bool = True) -> str:
    """format a tool result summary."""
    icon = "✅" if success else "❌"
    truncated = _truncate(result, 200)
    return f"{icon} `{name}`: {truncated}"


def paginate(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> List[str]:
    """split text into Telegram-safe pages."""
    if len(text) <= limit:
        return [text]
    pages = []
    while text:
        if len(text) <= limit:
            pages.append(text)
            break
        cut = text[:limit].rfind("\n")
        if cut < limit // 2:
            cut = limit
        pages.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return pages


def format_streaming_chunk(accumulated: str, new_chunk: str) -> str:
    """append chunk and return the updated accumulated text, truncated if needed."""
    accumulated += new_chunk
    if len(accumulated) > TELEGRAM_MSG_LIMIT - 100:
        accumulated = accumulated[-(TELEGRAM_MSG_LIMIT - 200):]
    return accumulated


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."
