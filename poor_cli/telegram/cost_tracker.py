"""Cost tracking per message and session."""

from typing import Any, Dict

from poor_cli.exceptions import setup_logger
from poor_cli.telegram.persistence import TelegramSessionStore
from poor_cli.telegram import formatter as fmt

logger = setup_logger(__name__)


class CostTracker:
    """tracks and reports token/cost usage per user and thread."""

    def __init__(self, store: TelegramSessionStore):
        self._store = store
        self._session_costs: Dict[int, Dict[str, float]] = {} # user_id -> running totals

    def track_cost(self, user_id: int, thread_id: str, event_data: Dict[str, Any]) -> None:
        inp = event_data.get("inputTokens", 0)
        out = event_data.get("outputTokens", 0)
        cost = event_data.get("estimatedCost", 0.0)
        self._store.record_cost(user_id, thread_id, inp, out, cost)
        if user_id not in self._session_costs:
            self._session_costs[user_id] = {"input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0}
        self._session_costs[user_id]["input_tokens"] += inp
        self._session_costs[user_id]["output_tokens"] += out
        self._session_costs[user_id]["estimated_cost_usd"] += cost

    def get_session_cost(self, user_id: int) -> Dict[str, Any]:
        return self._session_costs.get(user_id, {"input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0})

    def get_thread_cost(self, user_id: int, thread_id: str) -> Dict[str, Any]:
        return self._store.get_thread_cost(user_id, thread_id)

    def get_user_total_cost(self, user_id: int) -> Dict[str, Any]:
        return self._store.get_user_cost(user_id)

    def format_cost_summary(self, cost_data: Dict[str, Any]) -> str:
        return fmt.format_cost(cost_data)

    def reset_session(self, user_id: int) -> None:
        self._session_costs.pop(user_id, None)
