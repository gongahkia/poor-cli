from __future__ import annotations

from poor_cli.server.registry import register, rpc
from .common import CommonHandlersMixin
from .tools import ToolsHandlersMixin
from .status import StatusHandlersMixin
from .audit import AuditHandlersMixin
from .chat import ChatHandlersMixin
from .chat_streaming import ChatStreamingHandlersMixin
from .config import ConfigHandlersMixin
from .context import ContextHandlersMixin
from .providers import ProvidersHandlersMixin
from .sessions import SessionsHandlersMixin
from .tasks import TasksHandlersMixin
from .automations import AutomationsHandlersMixin
from .checkpoints import CheckpointsHandlersMixin
from .services import ServicesHandlersMixin
from .cost import CostHandlersMixin
from .agents import AgentsHandlersMixin
from .profiles import ProfilesHandlersMixin
from .trust import TrustHandlersMixin
from .memory import MemoryHandlersMixin
from .deployment import DeploymentHandlersMixin
from .prompts import PromptsHandlersMixin
from .misc import MiscHandlersMixin
from .diff_review import DiffReviewHandlersMixin
from .timeline import TimelineHandlersMixin
from .watch import WatchHandlersMixin
from .plan import PlanHandlersMixin
from .branches import BranchesHandlersMixin
from .repo_map import RepoMapHandlersMixin
from .mcp import McpHandlersMixin


class HandlerMixin(
    CommonHandlersMixin,
    ToolsHandlersMixin,
    AuditHandlersMixin,
    StatusHandlersMixin,
    ChatHandlersMixin,
    ChatStreamingHandlersMixin,
    ConfigHandlersMixin,
    ContextHandlersMixin,
    ProvidersHandlersMixin,
    SessionsHandlersMixin,
    TasksHandlersMixin,
    AutomationsHandlersMixin,
    CheckpointsHandlersMixin,
    ServicesHandlersMixin,
    CostHandlersMixin,
    AgentsHandlersMixin,
    ProfilesHandlersMixin,
    TrustHandlersMixin,
    MemoryHandlersMixin,
    DeploymentHandlersMixin,
    PromptsHandlersMixin,
    MiscHandlersMixin,
    DiffReviewHandlersMixin,
    TimelineHandlersMixin,
    WatchHandlersMixin,
    PlanHandlersMixin,
    BranchesHandlersMixin,
    RepoMapHandlersMixin,
    McpHandlersMixin,
):
    pass


__all__ = ["HandlerMixin", "register", "rpc"]
