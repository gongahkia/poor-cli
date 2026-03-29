"""Format CoreEvent streams into Telegram-friendly messages."""

import re
from typing import Any, Dict, List, Optional

TELEGRAM_MSG_LIMIT = 4096


def escape_markdown_v2(text: str) -> str:
    """escape special chars for Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special)}])", r"\\\1", text)


def format_tool_call(name: str, args: dict) -> str:
    arg_str = ", ".join(f"{k}={_truncate(str(v), 80)}" for k, v in args.items())
    return f"🔧 `{name}({arg_str})`"


def format_tool_result(name: str, result: str, success: bool = True) -> str:
    icon = "✅" if success else "❌"
    truncated = _truncate(result, 200)
    return f"{icon} `{name}`: {truncated}"


def paginate(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> List[str]:
    if len(text) <= limit:
        return [text]
    pages: List[str] = []
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
    accumulated += new_chunk
    if len(accumulated) > TELEGRAM_MSG_LIMIT - 100:
        accumulated = accumulated[-(TELEGRAM_MSG_LIMIT - 200):]
    return accumulated


def format_cost(cost_data: Dict[str, Any]) -> str:
    inp = cost_data.get("input_tokens", 0)
    out = cost_data.get("output_tokens", 0)
    usd = cost_data.get("estimated_cost_usd", 0.0)
    return f"💰 tokens: {inp} in / {out} out | ${usd:.4f}"


def format_permission_request(tool_name: str, args: Dict[str, Any]) -> str:
    arg_preview = ", ".join(f"{k}={_truncate(str(v), 60)}" for k, v in list(args.items())[:5])
    return f"🔐 permission needed\n`{tool_name}({arg_preview})`\napprove or deny?"


def format_thread_list(threads: List[Dict[str, Any]]) -> str:
    if not threads:
        return "no threads"
    lines = []
    for t in threads:
        active = " 🟢" if t.get("active") else ""
        lines.append(f"• `{t['name']}`{active} — {t.get('message_count', 0)} msgs")
    return "\n".join(lines)


def format_skill_list(skills: List[Dict[str, Any]]) -> str:
    if not skills:
        return "no skills found"
    lines = []
    for s in skills:
        lines.append(f"• `{s['name']}` — {s.get('description', 'no description')}")
    return "\n".join(lines)


def format_heartbeat_summary(data: Dict[str, Any]) -> str:
    prompt = data.get("prompt", "default check")
    interval = data.get("interval_minutes", 0)
    return f"💓 heartbeat: every {interval}m\nprompt: {_truncate(prompt, 120)}"


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."
