from datetime import datetime
from uuid import uuid4

from service.storage.db import Database, utc_now_iso


class MemorySummariesRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _normalize_timestamp(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def _row_to_payload(self, row) -> dict:
        payload = dict(row)
        payload["created_at"] = self._normalize_timestamp(payload.get("created_at"))
        payload["updated_at"] = self._normalize_timestamp(payload.get("updated_at"))
        return payload

    def create_summary(
        self,
        *,
        client_id: str,
        conversation_id: str,
        context_version: str | None,
        summary: str,
        source: str | None,
    ) -> dict:
        now = utc_now_iso()
        summary_id = str(uuid4())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_summaries (
                    summary_id, client_id, conversation_id, context_version,
                    summary, source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_id,
                    client_id,
                    conversation_id,
                    context_version,
                    summary,
                    source,
                    now,
                    now,
                ),
            )
        return self.get_summary(summary_id)

    def get_summary(self, summary_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_summaries WHERE summary_id = ?",
                (summary_id,),
            ).fetchone()
        return self._row_to_payload(row) if row else None

    def list_summaries(
        self,
        *,
        client_id: str,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses = ["client_id = ?"]
        params: list[str | int] = [client_id]

        if conversation_id:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)

        query = "SELECT * FROM memory_summaries WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def get_latest_summary(self, *, client_id: str, conversation_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM memory_summaries
                WHERE client_id = ? AND conversation_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (client_id, conversation_id),
            ).fetchone()
        return self._row_to_payload(row) if row else None
