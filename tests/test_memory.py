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


def test_memory_store_supports_in_memory_sqlite_path():
    store = MemoryStore(":memory:")

    conversation_id = "conv-memory"
    store.append_message(conversation_id, "user", "hello")

    history = store.get_recent_messages(conversation_id)

    assert history == [{"role": "user", "content": "hello"}]
