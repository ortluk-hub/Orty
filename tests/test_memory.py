import sqlite3

from service.memory import MemoryStore


def test_memory_store_generates_and_reuses_conversation_id(tmp_path):
    db_path = tmp_path / "orty.db"
    store = MemoryStore(str(db_path))

    generated = store.ensure_conversation_id(None)
    assert generated

    reused = store.ensure_conversation_id("abc-123")
    assert reused == "abc-123"


def test_memory_store_persists_and_reads_recent_messages(tmp_path):
    db_path = tmp_path / "orty.db"
    store = MemoryStore(str(db_path))

    conversation_id = "conv-1"
    store.append_message(conversation_id, "user", "hello")
    store.append_message(conversation_id, "assistant", "hi")

    history = store.get_recent_messages(conversation_id)

    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_memory_store_initializes_sqlite_index(tmp_path):
    db_path = tmp_path / "orty.db"
    MemoryStore(str(db_path))

    with sqlite3.connect(db_path) as conn:
        indexes = conn.execute("PRAGMA index_list(messages)").fetchall()

    index_names = {row[1] for row in indexes}
    assert "idx_messages_conversation_id_id" in index_names
