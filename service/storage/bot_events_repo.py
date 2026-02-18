import json
from uuid import uuid4

from service.storage.db import SQLiteDB, utc_now_iso


class BotEventsRepository:
    def __init__(self, db: SQLiteDB):
        self.db = db

    def add_event(
        self,
        bot_id: str,
        owner_client_id: str,
        event_type: str,
        message: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        event_id = str(uuid4())
        created_at = utc_now_iso()
        payload_json = json.dumps(payload or {})
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_events (event_id, bot_id, owner_client_id, event_type, message, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, bot_id, owner_client_id, event_type, message, created_at, payload_json),
            )
        return {
            "event_id": event_id,
            "bot_id": bot_id,
            "owner_client_id": owner_client_id,
            "event_type": event_type,
            "message": message,
            "created_at": created_at,
            "payload": payload or {},
        }

    def list_events(self, bot_id: str, limit: int = 100) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, bot_id, owner_client_id, event_type, message, created_at, payload_json
                FROM bot_events
                WHERE bot_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (bot_id, limit),
            ).fetchall()
        events: list[dict] = []
        for row in reversed(rows):
            event = dict(row)
            event["payload"] = json.loads(event.pop("payload_json") or "{}")
            events.append(event)
        return events
