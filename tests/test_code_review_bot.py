import asyncio
import tempfile

from service.supervisor.bot_types import code_review


class StubMemoryStore:
    def get_recent_messages(self, conversation_id: str, limit: int = 10):
        return []


class StubEventWriter:
    def __init__(self):
        self.events = []

    def emit(self, **kwargs):
        self.events.append(kwargs)


def test_code_review_bot_clones_repository_via_to_thread(monkeypatch):
    captured = {}

    async def fake_to_thread(func, repository_url, branch):
        captured["func_name"] = func.__name__
        captured["repository_url"] = repository_url
        captured["branch"] = branch
        return tempfile.mkdtemp(prefix="orty-review-test-")

    monkeypatch.setattr(code_review.asyncio, "to_thread", fake_to_thread)

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


def test_code_review_bot_handles_invalid_numeric_config(monkeypatch):
    captured = {}

    async def fake_to_thread(func, repository_url, branch):
        return tempfile.mkdtemp(prefix="orty-review-test-")

    monkeypatch.setattr(code_review.asyncio, "to_thread", fake_to_thread)

    class CapturingMemoryStore(StubMemoryStore):
        def get_recent_messages(self, conversation_id: str, limit: int = 10):
            captured["history_limit"] = limit
            return []

    writer = StubEventWriter()

    asyncio.run(
        code_review.run_code_review_bot(
            bot_id="bot-1",
            owner_client_id="owner-1",
            config={
                "repository_url": ".",
                "conversation_id": "conv-1",
                "history_limit": None,
                "max_proposals": "invalid",
            },
            memory_store=CapturingMemoryStore(),
            event_writer=writer,
        )
    )

    assert captured["history_limit"] == 20
    proposal_event = next(event for event in writer.events if event["event_type"] == "REVIEW_PROPOSAL")
    assert len(proposal_event["payload"]["proposals"]) == 3
