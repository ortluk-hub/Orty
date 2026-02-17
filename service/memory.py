import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from service.config import settings


class MemoryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.SQLITE_PATH
        self.timeout_seconds = settings.SQLITE_TIMEOUT_SECONDS
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.timeout_seconds)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id
                ON messages (conversation_id, id)
                """
            )

    def ensure_conversation_id(self, conversation_id: str | None) -> str:
        if conversation_id:
            return conversation_id
        return str(uuid4())

    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                (conversation_id, role, content),
            )

    def get_recent_messages(self, conversation_id: str, limit: int = 10) -> List[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()

        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]
