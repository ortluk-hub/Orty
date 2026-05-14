import json
from datetime import datetime
from uuid import uuid4

from service.storage.db import Database, utc_now_iso

_UNSET = object()


class MemoryRecordsRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _encode_tags(tags: list[str] | None) -> str:
        return json.dumps(tags or [])

    @staticmethod
    def _decode_tags(value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return json.loads(value or "[]")

    @staticmethod
    def _normalize_timestamp(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def _row_to_payload(self, row) -> dict:
        payload = dict(row)
        payload["tags"] = self._decode_tags(payload.pop("tags_json", None))
        payload["is_pinned"] = bool(payload.get("is_pinned"))
        payload["created_at"] = self._normalize_timestamp(payload.get("created_at"))
        payload["updated_at"] = self._normalize_timestamp(payload.get("updated_at"))
        payload["deleted_at"] = self._normalize_timestamp(payload.get("deleted_at"))
        return payload

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
                    self._encode_tags(tags),
                    importance,
                    source,
                    external_key,
                    bool(is_pinned),
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
        return self._row_to_payload(row)

    def get_active_record(self, record_id: str) -> dict | None:
        record = self.get_record(record_id)
        if not record or record.get("deleted_at") is not None:
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
        params: list[object] = [client_id]

        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if tag:
            if getattr(self.db, "kind", None) == "postgres":
                clauses.append("tags_json @> ?::jsonb")
                params.append(json.dumps([tag]))
            else:
                clauses.append("EXISTS (SELECT 1 FROM json_each(memory_records.tags_json) WHERE value = ?)")
                params.append(tag)

        query = "SELECT * FROM memory_records WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return [self._row_to_payload(row) for row in rows]

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
            params.append(self._encode_tags(tags))
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
            params.append(bool(is_pinned))
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
        return self._row_to_payload(row)

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
                        self._encode_tags(tags),
                        importance,
                        source,
                        external_key,
                        bool(is_pinned),
                        expires_at,
                        source_created_at,
                        source_updated_at,
                        now,
                        row["record_id"],
                    ),
                )
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
                        self._encode_tags(tags),
                        importance,
                        source,
                        external_key,
                        bool(is_pinned),
                        expires_at,
                        source_created_at,
                        source_updated_at,
                        now,
                        now,
                    ),
                )
        return self.get_active_record_by_external_key(client_id=client_id, external_key=external_key)

    def list_active_sync_records(self, *, client_id: str, source: str, limit: int | None = 200) -> list[dict]:
        params: list[object] = [client_id, source]
        limit_clause = ""
        if limit is not None:
            limit_clause = " LIMIT ?"
            params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM memory_records
                WHERE client_id = ? AND source = ? AND deleted_at IS NULL
                ORDER BY updated_at DESC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_payload(row) for row in rows]

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
