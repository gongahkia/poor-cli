"""Per-user conversation thread management."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from poor_cli.core import PoorCLICore
from poor_cli.exceptions import setup_logger
from poor_cli.telegram.persistence import TelegramSessionStore

logger = setup_logger(__name__)

DEFAULT_THREAD = "default"


class ThreadManager:
    """manages per-user conversation threads, each backed by a separate PoorCLICore."""

    def __init__(self, store: TelegramSessionStore, config_path: Optional[Path] = None):
        self._store = store
        self._config_path = config_path
        self._cores: Dict[str, PoorCLICore] = {} # "uid:thread_id" -> core
        self._active: Dict[int, str] = {} # user_id -> active thread_id

    def _key(self, user_id: int, thread_id: str) -> str:
        return f"{user_id}:{thread_id}"

    def create_thread(self, user_id: int, name: Optional[str] = None) -> str:
        thread_id = name or f"t-{uuid.uuid4().hex[:8]}"
        self._store.save_session(user_id, thread_id)
        self._active[user_id] = thread_id
        logger.info("created thread %s for user %d", thread_id, user_id)
        return thread_id

    def switch_thread(self, user_id: int, thread_id: str) -> bool:
        existing = self._store.load_session(user_id, thread_id)
        if existing is None:
            return False
        self._active[user_id] = thread_id
        logger.info("user %d switched to thread %s", user_id, thread_id)
        return True

    def list_threads(self, user_id: int) -> List[Dict[str, Any]]:
        threads = self._store.list_user_threads(user_id)
        active_id = self._active.get(user_id, DEFAULT_THREAD)
        for t in threads:
            t["active"] = t["thread_id"] == active_id
            t["name"] = t["thread_id"]
        return threads

    def archive_thread(self, user_id: int, thread_id: str) -> bool:
        key = self._key(user_id, thread_id)
        if key in self._cores:
            del self._cores[key]
        success = self._store.delete_thread(user_id, thread_id)
        if self._active.get(user_id) == thread_id:
            self._active.pop(user_id, None)
        return success

    def get_active_thread(self, user_id: int) -> str:
        if user_id not in self._active:
            threads = self._store.list_user_threads(user_id)
            if threads:
                self._active[user_id] = threads[0]["thread_id"]
            else:
                tid = self.create_thread(user_id, DEFAULT_THREAD)
                self._active[user_id] = tid
        return self._active[user_id]

    def get_core(self, user_id: int, thread_id: Optional[str] = None) -> PoorCLICore:
        tid = thread_id or self.get_active_thread(user_id)
        key = self._key(user_id, tid)
        if key not in self._cores:
            core = PoorCLICore(config_path=self._config_path)
            self._cores[key] = core
        return self._cores[key]

    async def ensure_initialized(self, core: PoorCLICore, provider_name: Optional[str] = None,
                                  model_name: Optional[str] = None) -> None:
        if not core._initialized:
            await core.initialize(provider_name=provider_name, model_name=model_name)

    def update_session_meta(self, user_id: int, thread_id: str, core: PoorCLICore) -> None:
        """persist provider/model info after initialization."""
        if core._initialized and core.config:
            self._store.save_session(
                user_id, thread_id,
                provider=core.config.model.provider,
                model=core.config.model.model_name,
            )

    def evict_lru(self, max_cores: int = 20) -> None:
        """evict least-recently-used cores if over limit."""
        if len(self._cores) <= max_cores:
            return
        keys = list(self._cores.keys())
        for k in keys[:len(keys) - max_cores]:
            del self._cores[k]
            logger.info("evicted core %s", k)

    def get_all_cores(self) -> List[PoorCLICore]:
        """return all active PoorCLICore instances."""
        return list(self._cores.values())

    def get_thread_count(self, user_id: int) -> int:
        return len(self._store.list_user_threads(user_id))
