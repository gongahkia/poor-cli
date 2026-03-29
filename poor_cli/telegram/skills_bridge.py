"""Expose poor-cli skills via Telegram."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from poor_cli.exceptions import setup_logger
from poor_cli.skills import SkillRegistry
from poor_cli.telegram import formatter as fmt
from poor_cli.telegram.keyboards import skill_keyboard

logger = setup_logger(__name__)

try:
    from telegram import Update
    from telegram.ext import ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


class SkillsBridge:
    """bridge between Telegram commands and the poor-cli skill system."""

    def __init__(self, repo_root: Optional[Path] = None):
        self._registry = SkillRegistry(repo_root=repo_root)

    def list_skills(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._registry.list_skills()]

    def get_skill_info(self, name: str) -> Optional[Dict[str, Any]]:
        s = self._registry.get_skill(name)
        if s is None:
            return None
        return s.to_dict()

    def render_skill_prompt(self, name: str, request: str) -> str:
        return self._registry.render_skill_prompt(name, request)

    async def handle_skill_command(self, update: Any, context: Any, args: List[str]) -> None:
        """dispatch /skill subcommands: list, run, info."""
        if not args:
            await update.message.reply_text("usage: /skill list | /skill run <name> [args] | /skill info <name>")
            return
        sub = args[0].lower()
        if sub == "list":
            skills = self.list_skills()
            text = fmt.format_skill_list(skills)
            kb = skill_keyboard(skills) if skills else None
            await update.message.reply_text(text, reply_markup=kb)
        elif sub == "info" and len(args) > 1:
            info = self.get_skill_info(args[1])
            if info:
                desc = info.get("description", "no description")
                await update.message.reply_text(f"🛠 `{info['name']}`\n{desc}")
            else:
                await update.message.reply_text(f"skill `{args[1]}` not found")
        elif sub == "run" and len(args) > 1:
            name = args[1]
            request = " ".join(args[2:]) if len(args) > 2 else ""
            try:
                prompt = self.render_skill_prompt(name, request)
                await update.message.reply_text(f"🛠 running skill `{name}`...\nprompt ready ({len(prompt)} chars)")
            except FileNotFoundError:
                await update.message.reply_text(f"skill `{name}` not found")
            except Exception as e:
                await update.message.reply_text(f"❌ skill error: {e}")
        else:
            await update.message.reply_text("usage: /skill list | /skill run <name> [args] | /skill info <name>")
