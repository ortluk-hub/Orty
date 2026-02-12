import tempfile
import sqlite3
import pytest

from service.storage.sqlite import init_db, EXPECTED_SCHEMA_VERSION


def get_version(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def test_fresh_db_sets_version():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name

    init_db(db_path)

    version = get_version(db_path)
    assert version == EXPECTED_SCHEMA_VERSION


def test_existing_db_with_correct_version_passes():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name

    init_db(db_path)

    # Should not raise
    init_db(db_path)


def test_existing_db_with_wrong_version_raises():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name

    init_db(db_path)

    # Manually corrupt version
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE schema_version SET version = ?", (999,))
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError):
        init_db(db_path)

