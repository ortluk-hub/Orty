import hashlib
import json
import secrets
from uuid import uuid4

from service.storage.db import SQLiteDB, utc_now_iso


class ClientsRepository:
    def __init__(self, db: SQLiteDB):
        self.db = db

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_client(self, name: str | None = None, *, preferences: dict | None = None, is_primary: bool = False) -> dict:
        client_id = str(uuid4())
        raw_token = secrets.token_urlsafe(32)
        token_hash = self.hash_token(raw_token)
        created_at = utc_now_iso()
        preferences_json = json.dumps(preferences or {}, sort_keys=True)

        with self.db.connect() as conn:
            if is_primary:
                conn.execute("UPDATE clients SET is_primary = 0 WHERE is_primary = 1")
            conn.execute(
                """
                INSERT INTO clients (client_id, name, token_hash, preferences_json, is_primary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (client_id, name, token_hash, preferences_json, 1 if is_primary else 0, created_at),
            )

        return {
            "client_id": client_id,
            "client_token": raw_token,
            "name": name,
            "preferences": preferences or {},
            "is_primary": is_primary,
            "created_at": created_at,
        }

    def list_clients(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT client_id, name, preferences_json, is_primary, created_at, last_seen_at FROM clients ORDER BY created_at DESC"
            ).fetchall()
        clients: list[dict] = []
        for row in rows:
            payload = dict(row)
            payload["preferences"] = json.loads(payload.pop("preferences_json") or "{}")
            payload["is_primary"] = bool(payload["is_primary"])
            clients.append(payload)
        return clients

    def verify_client_token(self, client_id: str, token: str) -> bool:
        token_hash = self.hash_token(token)
        now = utc_now_iso()
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT token_hash FROM clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not row or row["token_hash"] != token_hash:
                return False
            conn.execute("UPDATE clients SET last_seen_at = ? WHERE client_id = ?", (now, client_id))
            return True

    def get_client(self, client_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT client_id, name, preferences_json, is_primary, created_at, last_seen_at FROM clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["preferences"] = json.loads(payload.pop("preferences_json") or "{}")
        payload["is_primary"] = bool(payload["is_primary"])
        return payload

    def get_primary_client(self) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT client_id, name, preferences_json, is_primary, created_at, last_seen_at FROM clients WHERE is_primary = 1 LIMIT 1"
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["preferences"] = json.loads(payload.pop("preferences_json") or "{}")
        payload["is_primary"] = bool(payload["is_primary"])
        return payload

    def update_preferences(self, client_id: str, preferences: dict) -> dict | None:
        preferences_json = json.dumps(preferences, sort_keys=True)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE clients SET preferences_json = ? WHERE client_id = ?",
                (preferences_json, client_id),
            )
        return self.get_client(client_id)
