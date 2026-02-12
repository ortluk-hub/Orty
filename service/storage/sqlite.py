import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path("orty.db")

EXPECTED_SCHEMA_VERSION = 1

def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None):
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
    )
    """)


    # Create schema_version table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)

    # Check version
    cursor.execute("SELECT version FROM schema_version")
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (EXPECTED_SCHEMA_VERSION,)
        )
    elif row[0] != EXPECTED_SCHEMA_VERSION:
        raise RuntimeError(
            f"Schema version mismatch. Expected {EXPECTED_SCHEMA_VERSION}, found {row[0]}"
        )
    conn.commit()
    conn.close()

