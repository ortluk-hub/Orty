import json
from uuid import uuid4

from service.storage.db import SQLiteDB, utc_now_iso

_UNSET = object()


class MemoryRecordsRepository:
    def __init__(self, db: SQLiteDB):
        self.db = db

    def create_record(
        self,
        *,
        client_id: str,
        memory_type: str,
        content: str,
        summary: str | None,
        tags: list[str],
        importance: float,
        source: str | None,
    ) -> dict:
        now = utc_now_iso()
        record_id = str(uuid4())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_records (
                    record_id, client_id, memory_type, content, summary, tags_json,
                    importance, source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    client_id,
                    memory_type,
                    content,
                    summary,
                    json.dumps(tags),
                    importance,
                    source,
                    now,
                    now,
                ),
            )
        return self.get_record(record_id)

    def get_record(self, record_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["tags"] = json.loads(payload.pop("tags_json") or "[]")
        return payload

    def get_active_record(self, record_id: str) -> dict | None:
        record = self.get_record(record_id)
        if not record:
            return None
        if record.get("deleted_at") is not None:
            return None
        return record

    def list_records(
        self,
        *,
        client_id: str,
        memory_type: str | None = None,
        tag: str | None = None,
        source: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses = ["client_id = ?", "deleted_at IS NULL"]
        params: list[str | int] = [client_id]

        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)
        if source:
            clauses.append("source = ?")
            params.append(source)

        query = "SELECT * FROM memory_records WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        results: list[dict] = []
        for row in rows:
            payload = dict(row)
            payload["tags"] = json.loads(payload.pop("tags_json") or "[]")
            if tag and tag not in payload["tags"]:
                continue
            results.append(payload)
        return results

    def update_record(
        self,
        record_id: str,
        *,
        memory_type: str | None | object = _UNSET,
        content: str | None | object = _UNSET,
        summary: str | None | object = _UNSET,
        tags: list[str] | None | object = _UNSET,
        importance: float | None | object = _UNSET,
        source: str | None | object = _UNSET,
    ) -> dict | None:
        updates: list[str] = []
        params: list[object] = []

        if memory_type is not _UNSET:
            updates.append("memory_type = ?")
            params.append(memory_type)
        if content is not _UNSET:
            updates.append("content = ?")
            params.append(content)
        if summary is not _UNSET:
            updates.append("summary = ?")
            params.append(summary)
        if tags is not _UNSET:
            updates.append("tags_json = ?")
            params.append(json.dumps(tags))
        if importance is not _UNSET:
            updates.append("importance = ?")
            params.append(importance)
        if source is not _UNSET:
            updates.append("source = ?")
            params.append(source)

        if not updates:
            return self.get_active_record(record_id)

        now = utc_now_iso()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(record_id)

        query = "UPDATE memory_records SET " + ", ".join(updates) + " WHERE record_id = ? AND deleted_at IS NULL"
        with self.db.connect() as conn:
            result = conn.execute(query, tuple(params))
            if result.rowcount < 1:
                return None
        return self.get_active_record(record_id)

    def soft_delete_record(self, record_id: str) -> bool:
        now = utc_now_iso()
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE memory_records
                SET deleted_at = ?, updated_at = ?
                WHERE record_id = ? AND deleted_at IS NULL
                """,
                (now, now, record_id),
            )
            return result.rowcount > 0
