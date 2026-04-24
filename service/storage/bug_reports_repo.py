import json
from datetime import datetime
from uuid import uuid4

from service.storage.db import Database, utc_now_iso


class BugReportsRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_report(
        self,
        *,
        client_id: str,
        client: str | None,
        source: str | None,
        title: str,
        summary: str,
        details: str,
        metadata: dict[str, str] | None = None,
        source_created_at: int | None = None,
    ) -> dict:
        report_id = str(uuid4())
        now = utc_now_iso()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO bug_reports (
                    report_id, client_id, client, source, title, summary, details,
                    metadata_json, source_created_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    client_id,
                    client,
                    source,
                    title,
                    summary,
                    details,
                    json.dumps(metadata or {}, sort_keys=True),
                    source_created_at,
                    now,
                    now,
                ),
            )
        return self.get_report(report_id)

    def get_report(self, report_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM bug_reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_payload(row)

    def list_reports(
        self,
        *,
        client_id: str | None = None,
        limit: int = 50,
        source: str | None = None,
    ) -> list[dict]:
        clauses = []
        params: list[str | int] = []

        if client_id:
            clauses.append("client_id = ?")
            params.append(client_id)
        if source:
            clauses.append("source = ?")
            params.append(source)

        where_clause = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = "SELECT * FROM bug_reports" + where_clause
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def _row_to_payload(self, row) -> dict:
        payload = dict(row)
        payload["metadata"] = self._parse_json_field(payload.pop("metadata_json", None))
        payload["createdAt"] = payload.pop("source_created_at") or self._iso_to_epoch_ms(payload["created_at"])
        payload["created_at"] = self._normalize_timestamp(payload.get("created_at"))
        payload["updated_at"] = self._normalize_timestamp(payload.get("updated_at"))
        return payload

    def update_bug_status(
        self,
        report_id: str,
        status: str,
        codey_task_id: str | None = None,
    ) -> None:
        now = utc_now_iso()
        with self.db.connect() as conn:
            if codey_task_id:
                conn.execute(
                    """
                    UPDATE bug_reports
                    SET status = ?, codey_status = ?, codey_task_id = ?, updated_at = ?
                    WHERE report_id = ?
                    """,
                    (status, status, codey_task_id, now, report_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE bug_reports
                    SET status = ?, codey_status = ?, updated_at = ?
                    WHERE report_id = ?
                    """,
                    (status, status, now, report_id),
                )

    @staticmethod
    def _parse_json_field(value):
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return json.loads(value or "{}")

    @staticmethod
    def _normalize_timestamp(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @staticmethod
    def _iso_to_epoch_ms(value) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, datetime):
            return int(value.timestamp() * 1000)
        return int(datetime.fromisoformat(value).timestamp() * 1000)
