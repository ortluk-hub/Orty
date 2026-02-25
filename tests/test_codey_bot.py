import asyncio

from service.supervisor.bot_types import codey


class StubMemoryStore:
    def get_recent_messages(self, conversation_id: str, limit: int = 10):
        return []


class StubEventWriter:
    def __init__(self):
        self.events = []

    def emit(self, **kwargs):
        self.events.append(kwargs)


def test_normalized_modes_defaults_and_filters_unknowns():
    assert codey._normalized_modes(None) == codey.DEFAULT_MODES
    assert codey._normalized_modes(["Conversation", "unknown", "code review"]) == [
        "conversation",
        "code_review",
    ]


def test_run_codey_bot_emits_architecture_spec():
    writer = StubEventWriter()

    asyncio.run(
        codey.run_codey_bot(
            bot_id="bot-1",
            owner_client_id="owner-1",
            config={
                "working_title": "Codey",
                "intent_model": "gwen3:0.6b",
                "main_model": "qwen3-coder:480b",
                "fallback_model": "qwen2.5:1.5b",
                "modes": ["conversation", "debugging"],
            },
            memory_store=StubMemoryStore(),
            event_writer=writer,
        )
    )

    event_types = [event["event_type"] for event in writer.events]
    assert event_types == [
        "CODEY_PLANNING_STARTED",
        "CODEY_ARCHITECTURE_DRAFTED",
        "CODEY_COMPLETED",
    ]

    draft_payload = writer.events[1]["payload"]
    assert draft_payload["intent_resolver"]["model"] == "gwen3:0.6b"
    assert draft_payload["main_llm"]["model"] == "qwen3-coder:480b"
    assert draft_payload["fallback_llm"]["model"] == "qwen2.5:1.5b"
    assert "debugging" in draft_payload["system_prompts"]["mode_prompts"]
    assert draft_payload["runtime_sandbox"]["executor"] == "docker"
    assert draft_payload["runtime_sandbox"]["internet_access"]["allow_github"] is True
    assert draft_payload["runtime_sandbox"]["internet_access"]["deny_other_domains_by_default"] is True
    assert "intent_resolver" in draft_payload["system_prompts"]
    assert draft_payload["implementation_notes"]
