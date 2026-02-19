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

    def append_message(self, conversation_id: str, role: str, content: str, client_id: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                'INSERT INTO messages (client_id, conversation_id, role, content) VALUES (?, ?, ?, ?)',
                (client_id, conversation_id, role, content),
            )

    def get_recent_messages(
        self,
        conversation_id: str,
        limit: int = 10,
        client_id: str | None = None,
    ) -> List[dict[str, str]]:
        with self._connect() as conn:
            if client_id is None:
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
            else:
                rows = conn.execute(
                    '''
                    SELECT role, content
                    FROM messages
                    WHERE conversation_id = ? AND client_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    (conversation_id, client_id, limit),
                ).fetchall()

        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]
