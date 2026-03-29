"""InlineKeyboardMarkup builders for Telegram bot interactions."""

from typing import Any, Dict, List, Optional

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    InlineKeyboardButton = None # type: ignore[assignment,misc]
    InlineKeyboardMarkup = None # type: ignore[assignment,misc]

PROVIDERS = ["gemini", "openai", "anthropic", "ollama", "groq", "deepseek"]
PROVIDER_MODELS: Dict[str, List[str]] = {
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "openai": ["gpt-4.1", "gpt-4.1-mini", "o4-mini", "gpt-4.1-nano"],
    "anthropic": ["claude-sonnet-4-20250514", "claude-haiku-35-20241022"],
    "ollama": ["llama3", "codellama", "mistral"],
    "groq": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
}


def permission_keyboard(prompt_id: str) -> "InlineKeyboardMarkup":
    """approve/deny buttons for tool execution."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"perm:approve:{prompt_id}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"perm:deny:{prompt_id}"),
        ],
        [
            InlineKeyboardButton("✅ Approve All", callback_data=f"perm:approve_all:{prompt_id}"),
        ],
    ])


def provider_keyboard() -> "InlineKeyboardMarkup":
    """grid of provider buttons."""
    buttons = []
    row: List[Any] = []
    for i, p in enumerate(PROVIDERS):
        row.append(InlineKeyboardButton(p, callback_data=f"provider:{p}"))
        if len(row) == 3 or i == len(PROVIDERS) - 1:
            buttons.append(row)
            row = []
    return InlineKeyboardMarkup(buttons)


def model_keyboard(provider: str) -> "InlineKeyboardMarkup":
    """model list for selected provider."""
    models = PROVIDER_MODELS.get(provider, [])
    buttons = []
    for m in models:
        buttons.append([InlineKeyboardButton(m, callback_data=f"model:{provider}:{m}")])
    buttons.append([InlineKeyboardButton("« Back", callback_data="provider:back")])
    return InlineKeyboardMarkup(buttons)


def thread_keyboard(threads: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """thread list with switch buttons."""
    buttons = []
    for t in threads:
        label = t["name"]
        if t.get("active"):
            label = f"🟢 {label}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"thread:{t['thread_id']}")])
    buttons.append([InlineKeyboardButton("+ New Thread", callback_data="thread:new")])
    return InlineKeyboardMarkup(buttons)


def action_keyboard() -> "InlineKeyboardMarkup":
    """retry/cancel/export/cost action buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Retry", callback_data="action:retry"),
            InlineKeyboardButton("🚫 Cancel", callback_data="action:cancel"),
        ],
        [
            InlineKeyboardButton("📤 Export", callback_data="action:export"),
            InlineKeyboardButton("💰 Cost", callback_data="action:cost"),
        ],
    ])


def confirm_keyboard(action_id: str) -> "InlineKeyboardMarkup":
    """generic confirm/cancel."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:yes:{action_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"confirm:no:{action_id}"),
        ],
    ])


def skill_keyboard(skills: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """skill selection buttons."""
    buttons = []
    for s in skills[:10]: # cap at 10 buttons
        buttons.append([InlineKeyboardButton(
            f"{s['name']}", callback_data=f"skill:{s['name']}"
        )])
    return InlineKeyboardMarkup(buttons)


def heartbeat_keyboard(user_id: int) -> "InlineKeyboardMarkup":
    """heartbeat management buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏸ Pause", callback_data=f"hb:pause:{user_id}"),
            InlineKeyboardButton("▶ Resume", callback_data=f"hb:resume:{user_id}"),
        ],
        [
            InlineKeyboardButton("🗑 Cancel", callback_data=f"hb:cancel:{user_id}"),
        ],
    ])


def parse_callback(data: str) -> Dict[str, str]:
    """parse callback_data into {action, ...} dict."""
    parts = data.split(":")
    if not parts:
        return {"action": "unknown"}
    result: Dict[str, str] = {"action": parts[0]}
    if len(parts) > 1:
        result["value"] = parts[1]
    if len(parts) > 2:
        result["extra"] = parts[2]
    return result
