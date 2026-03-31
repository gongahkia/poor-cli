"""Telegram command handlers for poor-cli feature parity."""

from poor_cli.telegram.commands.sessions import register as register_sessions
from poor_cli.telegram.commands.tasks import register as register_tasks
from poor_cli.telegram.commands.automations import register as register_automations
from poor_cli.telegram.commands.agents import register as register_agents
from poor_cli.telegram.commands.checkpoints import register as register_checkpoints
from poor_cli.telegram.commands.git import register as register_git
from poor_cli.telegram.commands.memory import register as register_memory
from poor_cli.telegram.commands.admin import register as register_admin
from poor_cli.telegram.commands.workflows import register as register_workflows


def register_all(app, bot_instance):
    """register all command handlers with the Telegram Application."""
    for reg in (register_sessions, register_tasks, register_automations,
                register_agents, register_checkpoints, register_git,
                register_memory, register_admin, register_workflows):
        reg(app, bot_instance)
