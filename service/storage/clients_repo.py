import hashlib
import secrets
from uuid import uuid4

from service.storage.db import SQLiteDB, utc_now_iso


class ClientsRepository:
    def __init__(self, db: SQLiteDB):
        self.db = db

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_client(self, name: str | None = None) -> dict:
        client_id = str(uuid4())
        raw_token = secrets.token_urlsafe(32)
        token_hash = self.hash_token(raw_token)
        created_at = utc_now_iso()

        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO clients (client_id, name, token_hash, created_at) VALUES (?, ?, ?, ?)",
                (client_id, name, token_hash, created_at),
            )

        return {
            "client_id": client_id,
            "client_token": raw_token,
            "name": name,
            "created_at": created_at,
        }

    def list_clients(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT client_id, name, created_at, last_seen_at FROM clients ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

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
                "SELECT client_id, name, created_at, last_seen_at FROM clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
        return dict(row) if row else None
