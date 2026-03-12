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
        external_key: str | None = None,
        is_pinned: bool = False,
        expires_at: int | None = None,
        source_created_at: int | None = None,
        source_updated_at: int | None = None,
    ) -> dict:
        now = utc_now_iso()
        record_id = str(uuid4())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_records (
                    record_id, client_id, memory_type, content, summary, tags_json,
                    importance, source, external_key, is_pinned, expires_at, source_created_at,
                    source_updated_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    external_key,
                    1 if is_pinned else 0,
                    expires_at,
                    source_created_at,
                    source_updated_at,
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
        payload["is_pinned"] = bool(payload.get("is_pinned"))
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
        external_key: str | None | object = _UNSET,
        is_pinned: bool | None | object = _UNSET,
        expires_at: int | None | object = _UNSET,
        source_created_at: int | None | object = _UNSET,
        source_updated_at: int | None | object = _UNSET,
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
        if external_key is not _UNSET:
            updates.append("external_key = ?")
            params.append(external_key)
        if is_pinned is not _UNSET:
            updates.append("is_pinned = ?")
            params.append(1 if is_pinned else 0)
        if expires_at is not _UNSET:
            updates.append("expires_at = ?")
            params.append(expires_at)
        if source_created_at is not _UNSET:
            updates.append("source_created_at = ?")
            params.append(source_created_at)
        if source_updated_at is not _UNSET:
            updates.append("source_updated_at = ?")
            params.append(source_updated_at)

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

    def get_active_record_by_external_key(self, *, client_id: str, external_key: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_records
                WHERE client_id = ? AND external_key = ? AND deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (client_id, external_key),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["tags"] = json.loads(payload.pop("tags_json") or "[]")
        payload["is_pinned"] = bool(payload.get("is_pinned"))
        return payload

    def upsert_sync_record(
        self,
        *,
        client_id: str,
        external_key: str,
        memory_type: str,
        content: str,
        summary: str | None,
        tags: list[str],
        importance: float,
        source: str,
        is_pinned: bool,
        expires_at: int | None,
        source_created_at: int | None,
        source_updated_at: int | None,
    ) -> dict:
        now = utc_now_iso()
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT record_id
                FROM memory_records
                WHERE client_id = ? AND external_key = ? AND deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (client_id, external_key),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE memory_records
                    SET memory_type = ?,
                        content = ?,
                        summary = ?,
                        tags_json = ?,
                        importance = ?,
                        source = ?,
                        external_key = ?,
                        is_pinned = ?,
                        expires_at = ?,
                        source_created_at = ?,
                        source_updated_at = ?,
                        updated_at = ?
                    WHERE record_id = ? AND deleted_at IS NULL
                    """,
                    (
                        memory_type,
                        content,
                        summary,
                        json.dumps(tags),
                        importance,
                        source,
                        external_key,
                        1 if is_pinned else 0,
                        expires_at,
                        source_created_at,
                        source_updated_at,
                        now,
                        row["record_id"],
                    ),
                )
                record_id = row["record_id"]
            else:
                record_id = str(uuid4())
                conn.execute(
                    """
                    INSERT INTO memory_records (
                        record_id, client_id, memory_type, content, summary, tags_json,
                        importance, source, external_key, is_pinned, expires_at,
                        source_created_at, source_updated_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(client_id, external_key) WHERE deleted_at IS NULL AND external_key IS NOT NULL
                    DO UPDATE SET
                        memory_type = excluded.memory_type,
                        content = excluded.content,
                        summary = excluded.summary,
                        tags_json = excluded.tags_json,
                        importance = excluded.importance,
                        source = excluded.source,
                        is_pinned = excluded.is_pinned,
                        expires_at = excluded.expires_at,
                        source_created_at = excluded.source_created_at,
                        source_updated_at = excluded.source_updated_at,
                        updated_at = excluded.updated_at
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
                        external_key,
                        1 if is_pinned else 0,
                        expires_at,
                        source_created_at,
                        source_updated_at,
                        now,
                        now,
                    ),
                )
        return self.get_active_record_by_external_key(client_id=client_id, external_key=external_key)

    def list_active_sync_records(self, *, client_id: str, source: str, limit: int = 200) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_records
                WHERE client_id = ? AND source = ? AND deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (client_id, source, limit),
            ).fetchall()
        results: list[dict] = []
        for row in rows:
            payload = dict(row)
            payload["tags"] = json.loads(payload.pop("tags_json") or "[]")
            payload["is_pinned"] = bool(payload.get("is_pinned"))
            results.append(payload)
        return results

    def soft_delete_sync_records_missing_keys(
        self,
        *,
        client_id: str,
        source: str,
        keep_external_keys: list[str],
    ) -> int:
        now = utc_now_iso()
        with self.db.connect() as conn:
            if keep_external_keys:
                placeholders = ", ".join("?" for _ in keep_external_keys)
                result = conn.execute(
                    f"""
                    UPDATE memory_records
                    SET deleted_at = ?, updated_at = ?
                    WHERE client_id = ?
                      AND source = ?
                      AND deleted_at IS NULL
                      AND (external_key IS NULL OR external_key NOT IN ({placeholders}))
                    """,
                    (now, now, client_id, source, *keep_external_keys),
                )
            else:
                result = conn.execute(
                    """
                    UPDATE memory_records
                    SET deleted_at = ?, updated_at = ?
                    WHERE client_id = ?
                      AND source = ?
                      AND deleted_at IS NULL
                    """,
                    (now, now, client_id, source),
                )
            return result.rowcount
