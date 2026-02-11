import uuid
from typing import List, Dict, Optional
from service.storage.sqlite import get_connection


class ConversationRepository:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def create_conversation(self) -> str:
        conversation_id = str(uuid.uuid4())
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO conversations (id) VALUES (?)",
            (conversation_id,)
        )

        conn.commit()
        conn.close()

        return conversation_id

    def conversation_exists(self, conversation_id: str) -> bool:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM conversations WHERE id = ?",
            (conversation_id,)
        )

        row = cursor.fetchone()
        conn.close()

        return row is not None

    def add_message(self, conversation_id: str, role: str, content: str):
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (conversation_id, role, content)
        )

        conn.commit()
        conn.close()

    def get_messages(self, conversation_id: str) -> List[Dict]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,)
        )

        rows = cursor.fetchall()
        conn.close()

        return [{"role": row["role"], "content": row["content"]} for row in rows]

