"""SQLite-backed session store for Telegram bot."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)

DEFAULT_DB_PATH = Path.home() / ".poor-cli" / "telegram.db"


class TelegramSessionStore:
    """persistent session storage for Telegram bot using SQLite."""

    def __init__(self, db_path: Optional[Path] = None, pool_size: int = 3):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._pool: List[sqlite3.Connection] = []
        self._pool_size = pool_size
        self._lock = Lock()
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = None
        try:
            with self._lock:
                if self._pool:
                    conn = self._pool.pop()
                else:
                    conn = sqlite3.connect(str(self._db_path), timeout=30.0, check_same_thread=False)
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            if conn:
                with self._lock:
                    if len(self._pool) < self._pool_size:
                        self._pool.append(conn)
                    else:
                        conn.close()

    def _init_db(self) -> None:
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        user_id INTEGER NOT NULL,
                        thread_id TEXT NOT NULL,
                        provider TEXT DEFAULT '',
                        model TEXT DEFAULT '',
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        state BLOB,
                        PRIMARY KEY (user_id, thread_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sessions_user
                    ON sessions(user_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sessions_active
                    ON sessions(last_active)
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cost_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        thread_id TEXT NOT NULL,
                        input_tokens INTEGER DEFAULT 0,
                        output_tokens INTEGER DEFAULT 0,
                        estimated_cost REAL DEFAULT 0.0,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cost_user_thread
                    ON cost_records(user_id, thread_id)
                """)
                conn.commit()
                logger.info("telegram session db initialized at %s", self._db_path)
        except Exception as e:
            logger.error("failed to init telegram db: %s", e)

    def save_session(self, user_id: int, thread_id: str, provider: str = "",
                     model: str = "", state: Optional[bytes] = None) -> None:
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO sessions (user_id, thread_id, provider, model, last_active, state)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, thread_id) DO UPDATE SET
                        provider=excluded.provider, model=excluded.model,
                        last_active=excluded.last_active, state=excluded.state
                """, (user_id, thread_id, provider, model, datetime.now().isoformat(), state))
                conn.commit()
        except Exception as e:
            logger.error("save_session failed: %s", e)

    def load_session(self, user_id: int, thread_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._conn() as conn:
                cursor = conn.execute(
                    "SELECT provider, model, last_active, state FROM sessions WHERE user_id=? AND thread_id=?",
                    (user_id, thread_id),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {"provider": row[0], "model": row[1], "last_active": row[2], "state": row[3]}
        except Exception as e:
            logger.error("load_session failed: %s", e)
            return None

    def list_user_threads(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            with self._conn() as conn:
                cursor = conn.execute(
                    "SELECT thread_id, provider, model, last_active FROM sessions WHERE user_id=? ORDER BY last_active DESC",
                    (user_id,),
                )
                return [
                    {"thread_id": r[0], "provider": r[1], "model": r[2], "last_active": r[3]}
                    for r in cursor.fetchall()
                ]
        except Exception as e:
            logger.error("list_user_threads failed: %s", e)
            return []

    def delete_thread(self, user_id: int, thread_id: str) -> bool:
        try:
            with self._conn() as conn:
                conn.execute("DELETE FROM sessions WHERE user_id=? AND thread_id=?", (user_id, thread_id))
                conn.execute("DELETE FROM cost_records WHERE user_id=? AND thread_id=?", (user_id, thread_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error("delete_thread failed: %s", e)
            return False

    def cleanup_old(self, days: int = 30) -> int:
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            with self._conn() as conn:
                cursor = conn.execute("DELETE FROM sessions WHERE last_active < ?", (cutoff,))
                conn.execute("DELETE FROM cost_records WHERE timestamp < ?", (cutoff,))
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error("cleanup_old failed: %s", e)
            return 0

    def record_cost(self, user_id: int, thread_id: str, input_tokens: int = 0,
                    output_tokens: int = 0, estimated_cost: float = 0.0) -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO cost_records (user_id, thread_id, input_tokens, output_tokens, estimated_cost) VALUES (?,?,?,?,?)",
                    (user_id, thread_id, input_tokens, output_tokens, estimated_cost),
                )
                conn.commit()
        except Exception as e:
            logger.error("record_cost failed: %s", e)

    def get_thread_cost(self, user_id: int, thread_id: str) -> Dict[str, Any]:
        try:
            with self._conn() as conn:
                cursor = conn.execute(
                    "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(estimated_cost),0) "
                    "FROM cost_records WHERE user_id=? AND thread_id=?",
                    (user_id, thread_id),
                )
                row = cursor.fetchone()
                return {"input_tokens": row[0], "output_tokens": row[1], "estimated_cost_usd": row[2]}
        except Exception as e:
            logger.error("get_thread_cost failed: %s", e)
            return {"input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0}

    def get_user_cost(self, user_id: int) -> Dict[str, Any]:
        try:
            with self._conn() as conn:
                cursor = conn.execute(
                    "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(estimated_cost),0) "
                    "FROM cost_records WHERE user_id=?",
                    (user_id,),
                )
                row = cursor.fetchone()
                return {"input_tokens": row[0], "output_tokens": row[1], "estimated_cost_usd": row[2]}
        except Exception as e:
            logger.error("get_user_cost failed: %s", e)
            return {"input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0}

    def close_all(self) -> None:
        with self._lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()
