import asyncio

from service.supervisor.bot_types import automation_extensions


class StubMemoryStore:
    def get_recent_messages(self, conversation_id: str, limit: int = 10):
        return [
            {"role": "user", "content": "Need github automation and slack notifications."},
            {"role": "assistant", "content": "Let's prioritize github first."},
        ]


class StubEventWriter:
    def __init__(self):
        self.events = []

    def emit(self, **kwargs):
        self.events.append(kwargs)


def test_normalized_targets_deduplicates_and_falls_back():
    assert automation_extensions._normalized_targets(["GitHub", " github ", "", "slack"]) == ["github", "slack"]
    assert automation_extensions._normalized_targets([]) == automation_extensions.EXTENSION_FALLBACKS


def test_run_automation_extensions_bot_emits_plan_with_priorities():
    writer = StubEventWriter()

    asyncio.run(
        automation_extensions.run_automation_extensions_bot(
            bot_id="bot-1",
            owner_client_id="owner-1",
            config={"conversation_id": "conv-1", "integration_targets": ["github", "notion"]},
            memory_store=StubMemoryStore(),
            event_writer=writer,
        )
    )

    event_types = [event["event_type"] for event in writer.events]
    assert event_types == [
        "AUTOMATION_EXTENSIONS_STARTED",
        "AUTOMATION_EXTENSION_PLAN",
        "AUTOMATION_EXTENSIONS_COMPLETED",
    ]

    plan_payload = writer.events[1]["payload"]
    priorities = {item["target"]: item["priority"] for item in plan_payload["plans"]}
    assert priorities["github"] == "high"
    assert priorities["notion"] == "medium"


def test_run_automation_extensions_bot_handles_invalid_history_limit():
    writer = StubEventWriter()

    class CapturingMemoryStore(StubMemoryStore):
        def __init__(self):
            self.captured_limit = None

        def get_recent_messages(self, conversation_id: str, limit: int = 10):
            self.captured_limit = limit
            return super().get_recent_messages(conversation_id, limit=limit)

    memory_store = CapturingMemoryStore()

    asyncio.run(
        automation_extensions.run_automation_extensions_bot(
            bot_id="bot-1",
            owner_client_id="owner-1",
            config={"conversation_id": "conv-1", "history_limit": None},
            memory_store=memory_store,
            event_writer=writer,
        )
    )

    assert memory_store.captured_limit == 20
    assert writer.events[0]["event_type"] == "AUTOMATION_EXTENSIONS_STARTED"
