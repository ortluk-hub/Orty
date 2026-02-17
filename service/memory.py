import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from service.config import settings


class MemoryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.SQLITE_PATH
        self._use_uri = self.db_path.startswith("file:")
        self._is_memory_db = self.db_path == ":memory:" or (
            self._use_uri and "mode=memory" in self.db_path
        )
        self._persistent_conn: sqlite3.Connection | None = None

        if self._is_memory_db:
            self._persistent_conn = sqlite3.connect(
                self.db_path,
                uri=self._use_uri,
                check_same_thread=False,
            )

        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._persistent_conn is not None:
            yield self._persistent_conn
            return

        conn = sqlite3.connect(self.db_path, uri=self._use_uri)
        try:
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        if not self._is_memory_db:
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
            conn.commit()

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
            conn.commit()

    def get_recent_messages(self, conversation_id: str, limit: int = 10) -> list[dict[str, str]]:
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
