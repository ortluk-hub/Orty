import sqlite3
from contextlib import contextmanager
from pathlib import Path

from service.config import settings


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class SQLiteDB:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.SQLITE_PATH
        self.timeout_seconds = settings.SQLITE_TIMEOUT_SECONDS
        self.initialize()

    def _open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.timeout_seconds)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connect(self):
        conn = self._open_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            message_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "client_id" not in message_columns:
                conn.execute("ALTER TABLE messages ADD COLUMN client_id TEXT")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id
                ON messages (conversation_id, id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_client_conversation_id_id
                ON messages (client_id, conversation_id, id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    client_id TEXT PRIMARY KEY,
                    name TEXT,
                    token_hash TEXT NOT NULL,
                    preferences_json TEXT NOT NULL DEFAULT '{}',
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT
                )
                """
            )
            client_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(clients)").fetchall()
            }
            if "preferences_json" not in client_columns:
                conn.execute("ALTER TABLE clients ADD COLUMN preferences_json TEXT NOT NULL DEFAULT '{}'")
            if "is_primary" not in client_columns:
                conn.execute("ALTER TABLE clients ADD COLUMN is_primary INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_is_primary ON clients(is_primary) WHERE is_primary = 1")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS client_access_tokens (
                    token_hash TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    last_used_at TEXT,
                    FOREIGN KEY(client_id) REFERENCES clients(client_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_access_tokens_client_id ON client_access_tokens (client_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_access_tokens_expires_at ON client_access_tokens (expires_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_records (
                    record_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 0.5,
                    source TEXT,
                    external_key TEXT,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    expires_at INTEGER,
                    source_created_at INTEGER,
                    source_updated_at INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    FOREIGN KEY(client_id) REFERENCES clients(client_id)
                )
                """
            )
            memory_record_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(memory_records)").fetchall()
            }
            if "external_key" not in memory_record_columns:
                conn.execute("ALTER TABLE memory_records ADD COLUMN external_key TEXT")
            if "is_pinned" not in memory_record_columns:
                conn.execute("ALTER TABLE memory_records ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0")
            if "expires_at" not in memory_record_columns:
                conn.execute("ALTER TABLE memory_records ADD COLUMN expires_at INTEGER")
            if "source_created_at" not in memory_record_columns:
                conn.execute("ALTER TABLE memory_records ADD COLUMN source_created_at INTEGER")
            if "source_updated_at" not in memory_record_columns:
                conn.execute("ALTER TABLE memory_records ADD COLUMN source_updated_at INTEGER")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_records_client_created ON memory_records (client_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_records_client_type_created ON memory_records (client_id, memory_type, created_at)"
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_records_client_external_key
                ON memory_records (client_id, external_key)
                """
            )
            now = utc_now_iso()
            conn.execute(
                """
                UPDATE memory_records
                SET deleted_at = COALESCE(deleted_at, ?), updated_at = ?
                WHERE rowid IN (
                    SELECT older.rowid
                    FROM memory_records AS older
                    JOIN memory_records AS newer
                      ON older.client_id = newer.client_id
                     AND older.external_key = newer.external_key
                     AND older.external_key IS NOT NULL
                     AND older.deleted_at IS NULL
                     AND newer.deleted_at IS NULL
                     AND (
                         older.updated_at < newer.updated_at
                         OR (older.updated_at = newer.updated_at AND older.rowid < newer.rowid)
                     )
                )
                """,
                (now, now),
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_records_active_external_key
                ON memory_records (client_id, external_key)
                WHERE deleted_at IS NULL AND external_key IS NOT NULL
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_summaries (
                    summary_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    context_version TEXT,
                    summary TEXT NOT NULL,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(client_id) REFERENCES clients(client_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_summaries_client_conversation_created ON memory_summaries (client_id, conversation_id, created_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bug_reports (
                    report_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    client TEXT,
                    source TEXT,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    source_created_at INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(client_id) REFERENCES clients(client_id)
                )
                """
            )
            bug_report_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(bug_reports)").fetchall()
            }
            if "client" not in bug_report_columns:
                conn.execute("ALTER TABLE bug_reports ADD COLUMN client TEXT")
            if "source" not in bug_report_columns:
                conn.execute("ALTER TABLE bug_reports ADD COLUMN source TEXT")
            if "metadata_json" not in bug_report_columns:
                conn.execute("ALTER TABLE bug_reports ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
            if "source_created_at" not in bug_report_columns:
                conn.execute("ALTER TABLE bug_reports ADD COLUMN source_created_at INTEGER")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bug_reports_client_created ON bug_reports (client_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bug_reports_client_source_created ON bug_reports (client_id, source, created_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bots (
                    bot_id TEXT PRIMARY KEY,
                    owner_client_id TEXT NOT NULL,
                    bot_type TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(owner_client_id) REFERENCES clients(client_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_events (
                    event_id TEXT PRIMARY KEY,
                    bot_id TEXT NOT NULL,
                    owner_client_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT,
                    FOREIGN KEY(bot_id) REFERENCES bots(bot_id),
                    FOREIGN KEY(owner_client_id) REFERENCES clients(client_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bots_owner_client_id ON bots (owner_client_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bot_events_bot_id_created_at ON bot_events (bot_id, created_at)"
            )
