from service.storage import db as storage_db


class FakeCursor:
    def __init__(self):
        self.query = None
        self.params = None
        self.rowcount = 1
        self.description = [
            ("client_id", None, None, None, None, None, None),
            ("is_primary", None, None, None, None, None, None),
        ]

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return ("client-123", True)

    def fetchall(self):
        return [("client-123", True)]


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()

    def cursor(self):
        return self.cursor_instance


def test_build_database_prefers_explicit_sqlite_path(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_db.settings, "DATABASE_URL", "postgresql://example/orty")

    database = storage_db.build_database(str(tmp_path / "orty.db"))

    assert isinstance(database, storage_db.SQLiteDB)
    assert database.db_path == str(tmp_path / "orty.db")


def test_build_database_selects_postgres_when_database_url_is_present(monkeypatch):
    monkeypatch.setattr(storage_db.settings, "DATABASE_URL", "postgresql://example/orty")
    monkeypatch.setattr(storage_db.PostgresDB, "initialize", lambda self: None)

    database = storage_db.build_database()

    assert isinstance(database, storage_db.PostgresDB)
    assert database.database_url == "postgresql://example/orty"


def test_postgres_connection_translates_qmark_params_and_returns_mapping_rows():
    fake_connection = FakeConnection()
    adapter = storage_db.PostgresConnection(fake_connection)

    row = adapter.execute(
        "SELECT client_id, is_primary FROM clients WHERE client_id = ? AND is_primary = ?",
        ("client-123", True),
    ).fetchone()

    assert fake_connection.cursor_instance.query == (
        "SELECT client_id, is_primary FROM clients WHERE client_id = %s AND is_primary = %s"
    )
    assert fake_connection.cursor_instance.params == ("client-123", True)
    assert row["client_id"] == "client-123"
    assert row[1] is True
