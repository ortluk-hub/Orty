import asyncio
import tempfile

import pytest

from service.supervisor.bot_types import code_review


class StubMemoryStore:
    def get_recent_messages(self, conversation_id: str, limit: int = 10):
        return []


class StubEventWriter:
    def __init__(self):
        self.events = []

    def emit(self, **kwargs):
        self.events.append(kwargs)


def test_code_review_bot_clones_repository_without_blocking_event_loop(monkeypatch):
    captured = {}

    async def fake_clone_repo(repository_url, branch):
        captured["func_name"] = "_clone_repo"
        captured["repository_url"] = repository_url
        captured["branch"] = branch
        return tempfile.mkdtemp(prefix="orty-review-test-")

    monkeypatch.setattr(code_review, "_clone_repo", fake_clone_repo)

    writer = StubEventWriter()

    asyncio.run(
        code_review.run_code_review_bot(
            bot_id="bot-1",
            owner_client_id="owner-1",
            config={"repository_url": ".", "branch": "main"},
            memory_store=StubMemoryStore(),
            event_writer=writer,
        )
    )

    assert captured == {
        "func_name": "_clone_repo",
        "repository_url": ".",
        "branch": "main",
    }
    event_types = [event["event_type"] for event in writer.events]
    assert "REPO_CLONED" in event_types


def test_clone_repo_kills_process_on_asyncio_timeout(monkeypatch):
    class FakeProcess:
        def __init__(self):
            self.kill_called = False
            self.wait_called = False

        async def communicate(self):
            await asyncio.sleep(0)
            return b"", b""

        def kill(self):
            self.kill_called = True

        async def wait(self):
            self.wait_called = True

    process = FakeProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    async def fake_wait_for(awaitable, timeout):
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(code_review.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(code_review.asyncio, "wait_for", fake_wait_for)

    with pytest.raises(RuntimeError, match="Repository clone timed out"):
        asyncio.run(code_review._clone_repo("https://example.com/repo.git", "main"))

    assert process.kill_called is True
    assert process.wait_called is True
