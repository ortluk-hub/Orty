import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from service.config import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_add_column(conn: sqlite3.Connection, table: str, column_sql: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


class ResultRow(dict):
    def __init__(self, payload: dict[str, Any]):
        super().__init__(payload)
        self._keys = tuple(payload.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


class QueryResult:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return getattr(self._cursor, "rowcount", -1)

    def fetchone(self) -> ResultRow | None:
        row = self._cursor.fetchone()
        return self._coerce_row(row)

    def fetchall(self) -> list[ResultRow]:
        rows = self._cursor.fetchall()
        return [coerced for row in rows if (coerced := self._coerce_row(row)) is not None]

    def _coerce_row(self, row) -> ResultRow | None:
        if row is None:
            return None
        if isinstance(row, ResultRow):
            return row
        if isinstance(row, sqlite3.Row):
            return ResultRow({key: row[key] for key in row.keys()})
        if isinstance(row, dict):
            return ResultRow(dict(row))

        description = getattr(self._cursor, "description", None) or []
        keys: list[str] = []
        for column in description:
            if isinstance(column, (tuple, list)):
                keys.append(str(column[0]))
            else:
                keys.append(str(getattr(column, "name")))
        if keys:
            return ResultRow({key: value for key, value in zip(keys, row)})
        return ResultRow({f"col_{index}": value for index, value in enumerate(row)})


class DatabaseConnection:
    def execute(self, query: str, params: tuple | list | None = None) -> QueryResult:
        raise NotImplementedError


class Database:
    kind = "unknown"
    db_path: str | None = None
    database_url: str | None = None

    @contextmanager
    def connect(self) -> Iterator[DatabaseConnection]:
        raise NotImplementedError


class SQLiteConnection(DatabaseConnection):
    def __init__(self, raw_connection: sqlite3.Connection):
        self._raw_connection = raw_connection

    def execute(self, query: str, params: tuple | list | None = None) -> QueryResult:
        cursor = self._raw_connection.execute(query, tuple(params or ()))
        return QueryResult(cursor)


class PostgresConnection(DatabaseConnection):
    def __init__(self, raw_connection):
        self._raw_connection = raw_connection

    def execute(self, query: str, params: tuple | list | None = None) -> QueryResult:
        cursor = self._raw_connection.cursor()
        cursor.execute(_translate_qmark_params(query), tuple(params or ()))
        return QueryResult(cursor)


def _translate_qmark_params(query: str) -> str:
    return query.replace("?", "%s")


def _load_psycopg():
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only on Postgres path
        raise RuntimeError(
            "psycopg is required for PostgreSQL runtime. Install requirements.txt or unset DATABASE_URL."
        ) from exc
    return psycopg


class SQLiteDB(Database):
    kind = "sqlite"

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
    def connect(self) -> Iterator[DatabaseConnection]:
        conn = self._open_connection()
        try:
            yield SQLiteConnection(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._open_connection()
        try:
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
                _safe_add_column(conn, "clients", "preferences_json TEXT NOT NULL DEFAULT '{}'")
            if "is_primary" not in client_columns:
                _safe_add_column(conn, "clients", "is_primary INTEGER NOT NULL DEFAULT 0")
            if "is_admin" not in client_columns:
                _safe_add_column(conn, "clients", "is_admin INTEGER NOT NULL DEFAULT 0")
            if "access_tier" not in client_columns:
                _safe_add_column(conn, "clients", "access_tier TEXT NOT NULL DEFAULT 'free'")
            if "lifecycle_status" not in client_columns:
                _safe_add_column(conn, "clients", "lifecycle_status TEXT NOT NULL DEFAULT 'active'")
            if "revoked_at" not in client_columns:
                _safe_add_column(conn, "clients", "revoked_at TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_is_primary ON clients(is_primary) WHERE is_primary = 1"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS client_promotion_requests (
                    request_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewer_client_id TEXT,
                    rejection_reason TEXT,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    FOREIGN KEY(client_id) REFERENCES clients(client_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_promotion_requests_status ON client_promotion_requests (status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_promotion_requests_client_id ON client_promotion_requests (client_id)"
            )
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
            if "status" not in bug_report_columns:
                conn.execute("ALTER TABLE bug_reports ADD COLUMN status TEXT DEFAULT 'pending'")
            if "codey_task_id" not in bug_report_columns:
                conn.execute("ALTER TABLE bug_reports ADD COLUMN codey_task_id TEXT")
            if "codey_status" not in bug_report_columns:
                conn.execute("ALTER TABLE bug_reports ADD COLUMN codey_status TEXT")
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
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class PostgresDB(Database):
    kind = "postgres"

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or settings.DATABASE_URL
        if not self.database_url:
            raise ValueError("PostgreSQL runtime requires DATABASE_URL")
        self.connect_timeout_seconds = settings.DATABASE_CONNECT_TIMEOUT_SECONDS
        self.initialize()

    def _open_connection(self):
        psycopg = _load_psycopg()
        return psycopg.connect(self.database_url, connect_timeout=self.connect_timeout_seconds)

    @contextmanager
    def connect(self) -> Iterator[DatabaseConnection]:
        conn = self._open_connection()
        try:
            yield PostgresConnection(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        schema_path = Path(__file__).with_name("postgres_schema_phase1.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        conn = self._open_connection()
        try:
            conn.execute(schema_sql)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def build_database(db_path: str | None = None) -> Database:
    if db_path is not None:
        return SQLiteDB(db_path)
    if settings.DATABASE_URL:
        return PostgresDB(settings.DATABASE_URL)
    return SQLiteDB()
