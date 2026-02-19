import sqlite3
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

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.timeout_seconds)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

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
