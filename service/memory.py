from typing import List
from uuid import uuid4

from service.storage.db import SQLiteDB


class MemoryStore:
    def __init__(self, db_path: str | None = None):
        self.db = SQLiteDB(db_path)

    def _connect(self):
        return self.db.connect()

    def ensure_conversation_id(self, conversation_id: str | None) -> str:
        if conversation_id:
            return conversation_id
        return str(uuid4())

    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
                (conversation_id, role, content),
            )

    def get_recent_messages(self, conversation_id: str, limit: int = 10) -> List[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                '''
                SELECT role, content
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (conversation_id, limit),
            ).fetchall()

        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]
