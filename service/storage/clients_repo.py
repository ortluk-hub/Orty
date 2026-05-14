import hashlib
import logging
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from service.config import settings
from service.storage.db import Database, utc_now_iso


logger = logging.getLogger("orty.auth")


class ClientsRepository:
    STALE_AFTER = timedelta(days=30)
    ACCESS_TIERS = {"free", "premium", "dedicated", "enterprise"}

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_iso_datetime(raw: str | datetime) -> datetime:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(raw)

    @staticmethod
    def _serialize_json(value: dict | list) -> str:
        return json.dumps(value, sort_keys=True)

    @staticmethod
    def _deserialize_json(value, default):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value or json.dumps(default))

    @staticmethod
    def _normalize_timestamp(value: str | datetime | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @staticmethod
    def _short_client_id(client_id: str) -> str:
        value = (client_id or '').strip()
        return value[:8] if value else 'unknown'

    def _effective_lifecycle_status(self, payload: dict) -> str:
        stored_status = str(payload.get("lifecycle_status") or "active").strip().lower()
        if payload.get("revoked_at") or stored_status == "revoked":
            return "revoked"
        last_seen_at = payload.get("last_seen_at")
        if last_seen_at:
            seen_at = self._parse_iso_datetime(last_seen_at)
            if seen_at <= datetime.now(timezone.utc) - self.STALE_AFTER:
                return "stale"
        return "active"

    def _coerce_client_payload(self, row) -> dict | None:
        if not row:
            return None
        payload = dict(row)
        payload["preferences"] = self._deserialize_json(payload.pop("preferences_json"), {})
        payload["is_primary"] = bool(payload["is_primary"])
        payload["is_admin"] = bool(payload.get("is_admin"))
        payload["created_at"] = self._normalize_timestamp(payload.get("created_at"))
        payload["last_seen_at"] = self._normalize_timestamp(payload.get("last_seen_at"))
        payload["revoked_at"] = self._normalize_timestamp(payload.get("revoked_at"))
        payload["access_tier"] = str(payload.get("access_tier") or "free")
        payload["lifecycle_status"] = self._effective_lifecycle_status(payload)
        return payload

    def create_client(
        self,
        name: str | None = None,
        *,
        preferences: dict | None = None,
        is_primary: bool = False,
    ) -> dict:
        client_id = str(uuid4())
        raw_token = secrets.token_urlsafe(32)
        token_hash = self.hash_token(raw_token)
        created_at = utc_now_iso()
        preferences_json = self._serialize_json(preferences or {})

        with self.db.connect() as conn:
            if is_primary:
                conn.execute("UPDATE clients SET is_primary = ? WHERE is_primary = ?", (False, True))
            conn.execute(
                """
                INSERT INTO clients (client_id, name, token_hash, preferences_json, is_primary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (client_id, name, token_hash, preferences_json, bool(is_primary), created_at),
            )

        return {
            "client_id": client_id,
            "client_token": raw_token,
            "name": name,
            "preferences": preferences or {},
            "is_primary": is_primary,
            "access_tier": "free",
            "lifecycle_status": "active",
            "revoked_at": None,
            "created_at": created_at,
        }

    def register_alfred_client(
        self,
        *,
        name: str | None = None,
        preferences: dict | None = None,
    ) -> dict:
        merged_preferences = dict(preferences or {})
        merged_preferences.setdefault('client_family', 'alfred')
        merged_preferences.setdefault('registration_source', 'alfred-client-key')
        return self.create_client(name=name, preferences=merged_preferences)


    def list_clients(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT client_id, name, preferences_json, is_primary, is_admin, access_tier, lifecycle_status, revoked_at, created_at, last_seen_at
                FROM clients
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [payload for row in rows if (payload := self._coerce_client_payload(row)) is not None]

    def verify_client_token(self, client_id: str, token: str) -> bool:
        verified, _ = self.verify_client_token_with_reason(client_id, token)
        return verified

    def verify_client_token_with_reason(self, client_id: str, token: str) -> tuple[bool, str]:
        token_hash = self.hash_token(token)
        now = utc_now_iso()
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT token_hash, lifecycle_status, revoked_at FROM clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not row:
                return False, "client-not-found"
            if self._effective_lifecycle_status(dict(row)) == "revoked":
                return False, "client-revoked"
            if row["token_hash"] != token_hash:
                return False, "client-token-mismatch"
            conn.execute("UPDATE clients SET last_seen_at = ? WHERE client_id = ?", (now, client_id))
            return True, "ok"

    def issue_access_token(
        self,
        client_id: str,
        client_token: str,
        *,
        ttl_seconds: int | None = None,
    ) -> dict | None:
        token, _ = self.issue_access_token_with_reason(
            client_id,
            client_token,
            ttl_seconds=ttl_seconds,
        )
        return token

    def issue_access_token_with_reason(
        self,
        client_id: str,
        client_token: str,
        *,
        ttl_seconds: int | None = None,
    ) -> tuple[dict | None, str]:
        verified, reason = self.verify_client_token_with_reason(client_id, client_token)
        if not verified:
            logger.info(
                "auth_diag token_issue_rejected client_id=%s reason=%s",
                self._short_client_id(client_id),
                reason,
            )
            return None, reason

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
        }, "ok"

    def verify_access_token(self, access_token: str) -> dict | None:
        client, _ = self.verify_access_token_with_reason(access_token)
        return client

    def verify_access_token_with_reason(self, access_token: str) -> tuple[dict | None, str]:
        token_hash = self.hash_token(access_token)
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT t.client_id, t.expires_at, t.revoked_at, c.name, c.preferences_json, c.is_primary, c.is_admin, c.access_tier, c.lifecycle_status, c.revoked_at AS client_revoked_at, c.created_at, c.last_seen_at
                FROM client_access_tokens t
                JOIN clients c ON c.client_id = t.client_id
                WHERE t.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return None, "access-token-not-found"
            if row["revoked_at"] is not None:
                return None, "access-token-revoked"
            if self._effective_lifecycle_status(
                {
                    "lifecycle_status": row["lifecycle_status"],
                    "revoked_at": row["client_revoked_at"],
                    "last_seen_at": row["last_seen_at"],
                }
            ) == "revoked":
                return None, "client-revoked"

            expires_at = self._parse_iso_datetime(row["expires_at"])
            if expires_at <= now:
                return None, "access-token-expired"

            conn.execute(
                "UPDATE client_access_tokens SET last_used_at = ? WHERE token_hash = ?",
                (now_iso, token_hash),
            )
            conn.execute("UPDATE clients SET last_seen_at = ? WHERE client_id = ?", (now_iso, row["client_id"]))

        return self._coerce_client_payload(
            {
            "client_id": row["client_id"],
            "name": row["name"],
            "preferences_json": row["preferences_json"],
            "is_primary": row["is_primary"],
            "is_admin": row["is_admin"],
            "access_tier": row["access_tier"],
            "lifecycle_status": row["lifecycle_status"],
            "revoked_at": row["client_revoked_at"],
            "created_at": self._normalize_timestamp(row["created_at"]),
            "last_seen_at": now_iso,
            }
        ), "ok"

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
                "created_at": self._normalize_timestamp(row["created_at"]),
                "expires_at": self._normalize_timestamp(row["expires_at"]),
                "revoked_at": self._normalize_timestamp(row["revoked_at"]),
                "last_used_at": self._normalize_timestamp(row["last_used_at"]),
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
                """
                SELECT client_id, name, preferences_json, is_primary, is_admin, access_tier, lifecycle_status, revoked_at, created_at, last_seen_at
                FROM clients
                WHERE client_id = ?
                """,
                (client_id,),
            ).fetchone()
        return self._coerce_client_payload(row)

    def get_primary_client(self) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT client_id, name, preferences_json, is_primary, is_admin, access_tier, lifecycle_status, revoked_at, created_at, last_seen_at
                FROM clients
                WHERE is_primary = ?
                LIMIT 1
                """,
                (True,),
            ).fetchone()
        return self._coerce_client_payload(row)

    def update_preferences(self, client_id: str, preferences: dict) -> dict | None:
        preferences_json = self._serialize_json(preferences)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE clients SET preferences_json = ? WHERE client_id = ?",
                (preferences_json, client_id),
            )
        return self.get_client(client_id)

    def request_promotion(
        self,
        client_id: str,
        reason: str,
        admin_secret_hash: str,
    ) -> dict | None:
        from service.security import hash_token

        if admin_secret_hash != hash_token(settings.ORTY_SHARED_SECRET):
            return None

        request_id = str(uuid4())
        created_at = utc_now_iso()

        with self.db.connect() as conn:
            client = conn.execute(
                "SELECT client_id FROM clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not client:
                return None

            conn.execute(
                """
                INSERT INTO client_promotion_requests (
                    request_id, client_id, reason, status, created_at, reviewed_at
                )
                VALUES (?, ?, ?, 'pending', ?, NULL)
                """,
                (request_id, client_id, reason, created_at),
            )

        return {
            "request_id": request_id,
            "client_id": client_id,
            "reason": reason,
            "status": "pending",
            "created_at": created_at,
        }

    def get_promotion_requests(self, status: str | None = "pending") -> list[dict]:
        with self.db.connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT r.*, c.name as client_name
                    FROM client_promotion_requests r
                    JOIN clients c ON c.client_id = r.client_id
                    WHERE r.status = ?
                    ORDER BY r.created_at DESC
                    """,
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT r.*, c.name as client_name
                    FROM client_promotion_requests r
                    JOIN clients c ON c.client_id = r.client_id
                    ORDER BY r.created_at DESC
                    """
                ).fetchall()

        return [
            {
                **dict(row),
                "created_at": self._normalize_timestamp(row.get("created_at")),
                "reviewed_at": self._normalize_timestamp(row.get("reviewed_at")),
            }
            for row in rows
        ]

    def approve_promotion(self, request_id: str, reviewer_client_id: str) -> dict | None:
        reviewed_at = utc_now_iso()

        with self.db.connect() as conn:
            request = conn.execute(
                "SELECT client_id, status FROM client_promotion_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if not request or request["status"] != "pending":
                return None

            client_id = request["client_id"]
            client_row = conn.execute(
                "SELECT preferences_json FROM clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not client_row:
                return None

            merged_preferences = self._deserialize_json(client_row["preferences_json"], {})
            merged_preferences["promoted_at"] = reviewed_at

            conn.execute(
                """
                UPDATE client_promotion_requests
                SET status = 'approved', reviewed_at = ?, reviewer_client_id = ?
                WHERE request_id = ?
                """,
                (reviewed_at, reviewer_client_id, request_id),
            )
            conn.execute(
                """
                UPDATE clients
                SET is_admin = ?, preferences_json = ?
                WHERE client_id = ?
                """,
                (True, self._serialize_json(merged_preferences), client_id),
            )

        return self.get_client(client_id)

    def reject_promotion(self, request_id: str, reviewer_client_id: str, reason: str) -> dict | None:
        reviewed_at = utc_now_iso()

        with self.db.connect() as conn:
            request = conn.execute(
                "SELECT client_id, status FROM client_promotion_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if not request or request["status"] != "pending":
                return None

            conn.execute(
                """
                UPDATE client_promotion_requests
                SET status = 'rejected', reviewed_at = ?, reviewer_client_id = ?, rejection_reason = ?
                WHERE request_id = ?
                """,
                (reviewed_at, reviewer_client_id, reason, request_id),
            )

        rows = self.get_promotion_requests(status=None)
        return next((row for row in rows if row["request_id"] == request_id), None)

    def is_admin(self, client_id: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT is_admin FROM clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
        return bool(row and row["is_admin"])

    def get_admin_clients(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT client_id, name, preferences_json, is_primary, is_admin, access_tier, lifecycle_status, revoked_at, created_at, last_seen_at
                FROM clients
                WHERE is_admin = ?
                ORDER BY created_at DESC
                """,
                (True,),
            ).fetchall()

        return [payload for row in rows if (payload := self._coerce_client_payload(row)) is not None]

    def update_access_tier(self, client_id: str, access_tier: str) -> dict | None:
        normalized = str(access_tier or "").strip().lower()
        if normalized not in self.ACCESS_TIERS:
            raise ValueError(f"Unsupported access tier: {access_tier}")
        with self.db.connect() as conn:
            result = conn.execute(
                "UPDATE clients SET access_tier = ? WHERE client_id = ?",
                (normalized, client_id),
            )
            if result.rowcount < 1:
                return None
        return self.get_client(client_id)

    def revoke_client(self, client_id: str, *, revoke_access_tokens: bool = True) -> dict | None:
        revoked_at = utc_now_iso()
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE clients
                SET lifecycle_status = 'revoked', revoked_at = COALESCE(revoked_at, ?)
                WHERE client_id = ?
                """,
                (revoked_at, client_id),
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
                    (revoked_at, client_id),
                )
        return self.get_client(client_id)
