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
            InlineKeyboardButton("approve", callback_data=f"perm:approve:{prompt_id}"),
            InlineKeyboardButton("deny", callback_data=f"perm:deny:{prompt_id}"),
        ],
        [
            InlineKeyboardButton("approve all", callback_data=f"perm:approve_all:{prompt_id}"),
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
    buttons = [[InlineKeyboardButton(m, callback_data=f"model:{provider}:{m}")] for m in models]
    buttons.append([InlineKeyboardButton("back", callback_data="provider:back")])
    return InlineKeyboardMarkup(buttons)


def thread_keyboard(threads: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """thread list with switch buttons."""
    buttons = []
    for t in threads:
        label = t["name"]
        if t.get("active"):
            label = f"[active] {label}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"thread:{t['thread_id']}")])
    buttons.append([InlineKeyboardButton("+ new thread", callback_data="thread:new")])
    return InlineKeyboardMarkup(buttons)


def action_keyboard() -> "InlineKeyboardMarkup":
    """retry/cancel/export/cost action buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("retry", callback_data="action:retry"),
            InlineKeyboardButton("cancel", callback_data="action:cancel"),
        ],
        [
            InlineKeyboardButton("export", callback_data="action:export"),
            InlineKeyboardButton("cost", callback_data="action:cost"),
        ],
    ])


def skill_keyboard(skills: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """skill selection buttons."""
    buttons = [[InlineKeyboardButton(s['name'], callback_data=f"skill:{s['name']}")] for s in skills[:10]]
    return InlineKeyboardMarkup(buttons)


def heartbeat_keyboard(user_id: int) -> "InlineKeyboardMarkup":
    """heartbeat management buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("pause", callback_data=f"hb:pause:{user_id}"),
            InlineKeyboardButton("resume", callback_data=f"hb:resume:{user_id}"),
        ],
        [InlineKeyboardButton("cancel", callback_data=f"hb:cancel:{user_id}")],
    ])


# ── new keyboards for feature parity ──

def session_keyboard(sessions: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """session action buttons."""
    buttons = []
    for s in sessions[:8]:
        tid = s.get("thread_id", s.get("name", "?"))
        buttons.append([
            InlineKeyboardButton(f"switch {tid}", callback_data=f"sess:switch:{tid}"),
            InlineKeyboardButton("fork", callback_data=f"sess:fork:{tid}"),
            InlineKeyboardButton("destroy", callback_data=f"sess:destroy:{tid}"),
        ])
    buttons.append([InlineKeyboardButton("+ new session", callback_data="sess:create:")])
    return InlineKeyboardMarkup(buttons)


def task_keyboard(tasks: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """task action buttons."""
    buttons = []
    for t in tasks[:8]:
        tid = t.get("id", t.get("taskId", "?"))
        status = t.get("status", "?")
        row = [InlineKeyboardButton(f"{tid} [{status}]", callback_data=f"task:show:{tid}")]
        if status in ("pending", "queued"):
            row.append(InlineKeyboardButton("start", callback_data=f"task:start:{tid}"))
        elif status == "awaiting_approval":
            row.append(InlineKeyboardButton("approve", callback_data=f"task:approve:{tid}"))
        elif status == "running":
            row.append(InlineKeyboardButton("cancel", callback_data=f"task:cancel:{tid}"))
        elif status == "failed":
            row.append(InlineKeyboardButton("retry", callback_data=f"task:retry:{tid}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def automation_keyboard(automations: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """automation action buttons."""
    buttons = []
    for a in automations[:8]:
        aid = a.get("id", a.get("name", "?"))
        enabled = a.get("enabled", False)
        toggle = "disable" if enabled else "enable"
        buttons.append([
            InlineKeyboardButton(str(aid), callback_data=f"auto:show:{aid}"),
            InlineKeyboardButton(toggle, callback_data=f"auto:{toggle}:{aid}"),
            InlineKeyboardButton("run", callback_data=f"auto:run:{aid}"),
        ])
    return InlineKeyboardMarkup(buttons)


def agent_keyboard(agents: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """agent action buttons."""
    buttons = []
    for a in agents[:8]:
        aid = a.get("id", a.get("agentId", "?"))
        status = a.get("status", "?")
        row = [InlineKeyboardButton(f"{aid} [{status}]", callback_data=f"agent:show:{aid}")]
        if status == "running":
            row.append(InlineKeyboardButton("cancel", callback_data=f"agent:cancel:{aid}"))
        elif status in ("pending", "created"):
            row.append(InlineKeyboardButton("start", callback_data=f"agent:start:{aid}"))
        row.append(InlineKeyboardButton("logs", callback_data=f"agent:logs:{aid}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def checkpoint_keyboard(checkpoints: List[Dict[str, Any]]) -> "InlineKeyboardMarkup":
    """checkpoint action buttons."""
    buttons = []
    for c in checkpoints[:8]:
        cid = c.get("checkpointId", c.get("id", "?"))
        buttons.append([
            InlineKeyboardButton(f"preview {cid}", callback_data=f"cp:preview:{cid}"),
            InlineKeyboardButton("restore", callback_data=f"cp:restore:{cid}"),
        ])
    buttons.append([InlineKeyboardButton("gc", callback_data="cp:gc:")])
    return InlineKeyboardMarkup(buttons)


def git_keyboard() -> "InlineKeyboardMarkup":
    """git sub-command buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("status", callback_data="gitcmd:status:"),
            InlineKeyboardButton("log", callback_data="gitcmd:log:"),
            InlineKeyboardButton("diff", callback_data="gitcmd:diff:"),
        ],
        [
            InlineKeyboardButton("branches", callback_data="gitcmd:branches:"),
        ],
    ])


def economy_keyboard() -> "InlineKeyboardMarkup":
    """economy preset buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("none", callback_data="econ:none:"),
            InlineKeyboardButton("light", callback_data="econ:light:"),
        ],
        [
            InlineKeyboardButton("moderate", callback_data="econ:moderate:"),
            InlineKeyboardButton("aggressive", callback_data="econ:aggressive:"),
        ],
    ])


def parse_callback(data: str) -> Dict[str, str]:
    """parse callback_data into {action, value, extra} dict."""
    parts = data.split(":")
    if not parts:
        return {"action": "unknown"}
    result: Dict[str, str] = {"action": parts[0]}
    if len(parts) > 1:
        result["value"] = parts[1]
    if len(parts) > 2:
        result["extra"] = parts[2]
    return result
