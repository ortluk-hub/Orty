import json
from uuid import uuid4

from service.storage.db import SQLiteDB, utc_now_iso


class BugReportsRepository:
    def __init__(self, db: SQLiteDB):
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
        client_id: str,
        limit: int = 50,
        source: str | None = None,
    ) -> list[dict]:
        clauses = ["client_id = ?"]
        params: list[str | int] = [client_id]
        if source:
            clauses.append("source = ?")
            params.append(source)

        query = "SELECT * FROM bug_reports WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def _row_to_payload(self, row) -> dict:
        payload = dict(row)
        payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
        payload["createdAt"] = payload.pop("source_created_at") or self._iso_to_epoch_ms(payload["created_at"])
        return payload

    @staticmethod
    def _iso_to_epoch_ms(value: str) -> int:
        from datetime import datetime

        return int(datetime.fromisoformat(value).timestamp() * 1000)
