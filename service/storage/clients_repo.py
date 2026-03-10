import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from service.config import settings
from service.storage.db import SQLiteDB, utc_now_iso


class ClientsRepository:
    def __init__(self, db: SQLiteDB):
        self.db = db

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_iso_datetime(raw: str) -> datetime:
        return datetime.fromisoformat(raw)

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

    def issue_access_token(
        self,
        client_id: str,
        client_token: str,
        *,
        ttl_seconds: int | None = None,
    ) -> dict | None:
        if not self.verify_client_token(client_id, client_token):
            return None

        token = secrets.token_urlsafe(48)
        token_hash = self.hash_token(token)
        created_at = utc_now_iso()
        ttl = ttl_seconds if ttl_seconds is not None else settings.CLIENT_ACCESS_TOKEN_TTL_SECONDS
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO client_access_tokens (token_hash, client_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_hash, client_id, created_at, expires_at),
            )

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ttl,
            "expires_at": expires_at,
            "client_id": client_id,
        }

    def verify_access_token(self, access_token: str) -> dict | None:
        token_hash = self.hash_token(access_token)
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT t.client_id, t.expires_at, t.revoked_at, c.name, c.preferences_json, c.is_primary, c.created_at, c.last_seen_at
                FROM client_access_tokens t
                JOIN clients c ON c.client_id = t.client_id
                WHERE t.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            if row["revoked_at"] is not None:
                return None

            expires_at = self._parse_iso_datetime(row["expires_at"])
            if expires_at <= now:
                return None

            conn.execute(
                "UPDATE client_access_tokens SET last_used_at = ? WHERE token_hash = ?",
                (now_iso, token_hash),
            )
            conn.execute("UPDATE clients SET last_seen_at = ? WHERE client_id = ?", (now_iso, row["client_id"]))

        return {
            "client_id": row["client_id"],
            "name": row["name"],
            "preferences": json.loads(row["preferences_json"] or "{}"),
            "is_primary": bool(row["is_primary"]),
            "created_at": row["created_at"],
            "last_seen_at": now_iso,
        }

    def inspect_access_token(self, access_token: str) -> dict | None:
        token_hash = self.hash_token(access_token)
        now = datetime.now(timezone.utc)
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT token_hash, client_id, created_at, expires_at, revoked_at, last_used_at
                FROM client_access_tokens
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return None

            expires_at = self._parse_iso_datetime(row["expires_at"])
            is_revoked = row["revoked_at"] is not None
            is_expired = expires_at <= now

            return {
                "found": True,
                "active": (not is_revoked) and (not is_expired),
                "client_id": row["client_id"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "revoked_at": row["revoked_at"],
                "last_used_at": row["last_used_at"],
            }

    def revoke_access_token(self, access_token: str) -> bool:
        token_hash = self.hash_token(access_token)
        now = utc_now_iso()
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE client_access_tokens
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE token_hash = ?
                """,
                (now, token_hash),
            )
            return result.rowcount > 0

    def revoke_access_tokens_for_client(self, client_id: str) -> int:
        now = utc_now_iso()
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE client_access_tokens
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE client_id = ?
                """,
                (now, client_id),
            )
            return result.rowcount

    def rotate_client_token(
        self,
        client_id: str,
        current_client_token: str,
        *,
        revoke_access_tokens: bool = True,
    ) -> dict | None:
        if not self.verify_client_token(client_id, current_client_token):
            return None

        new_token = secrets.token_urlsafe(32)
        new_token_hash = self.hash_token(new_token)
        rotated_at = utc_now_iso()

        with self.db.connect() as conn:
            result = conn.execute(
                "UPDATE clients SET token_hash = ?, last_seen_at = ? WHERE client_id = ?",
                (new_token_hash, rotated_at, client_id),
            )
            if result.rowcount < 1:
                return None
            if revoke_access_tokens:
                conn.execute(
                    """
                    UPDATE client_access_tokens
                    SET revoked_at = COALESCE(revoked_at, ?)
                    WHERE client_id = ?
                    """,
                    (rotated_at, client_id),
                )

        return {
            "client_id": client_id,
            "client_token": new_token,
            "rotated_at": rotated_at,
        }

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
