from service.memory import MemoryStore
from service.supervisor.events import BotEventWriter


EXTENSION_FALLBACKS = [
    "github",
    "slack",
    "notion",
]


def _normalized_targets(raw_targets: list[str] | str | None) -> list[str]:
    if not raw_targets:
        return EXTENSION_FALLBACKS

    if isinstance(raw_targets, str):
        raw_targets = [raw_targets]

    normalized: list[str] = []
    seen: set[str] = set()
    for target in raw_targets:
        cleaned = str(target).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return normalized[:5] if normalized else EXTENSION_FALLBACKS


def _build_extension_steps(target: str, memory_text: str) -> list[str]:
    has_signal = target in memory_text
    return [
        f"Define `{target}` integration contract and required secrets.",
        f"Create `{target}` adapter interface with capability flags.",
        (
            f"Add `{target}` event flow tests using captured chat-memory scenarios."
            if has_signal
            else f"Add `{target}` event flow tests with synthetic fixtures."
        ),
    ]


def _safe_positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


async def run_automation_extensions_bot(
    bot_id: str,
    owner_client_id: str,
    config: dict,
    memory_store: MemoryStore,
    event_writer: BotEventWriter,
) -> None:
    conversation_id = config.get("conversation_id")
    history_limit = _safe_positive_int(config.get("history_limit", 20), default=20)

    extension_targets = _normalized_targets(config.get("integration_targets"))
    memory_messages: list[dict[str, str]] = []
    if conversation_id:
        memory_messages = memory_store.get_recent_messages(str(conversation_id), limit=history_limit)
    memory_text = "\n".join(message.get("content", "") for message in memory_messages).lower()

    event_writer.emit(
        bot_id=bot_id,
        owner_client_id=owner_client_id,
        event_type="AUTOMATION_EXTENSIONS_STARTED",
        message="Automation extensions planning started.",
        payload={"targets": extension_targets},
    )

    plans = []
    for target in extension_targets:
        plans.append(
            {
                "target": target,
                "priority": "high" if target in memory_text else "medium",
                "steps": _build_extension_steps(target, memory_text),
            }
        )

    event_writer.emit(
        bot_id=bot_id,
        owner_client_id=owner_client_id,
        event_type="AUTOMATION_EXTENSION_PLAN",
        message="Generated automation extension execution plan.",
        payload={
            "conversation_id": conversation_id,
            "considered_memory_messages": len(memory_messages),
            "plans": plans,
            "human_review_required": True,
        },
    )

    event_writer.emit(
        bot_id=bot_id,
        owner_client_id=owner_client_id,
        event_type="AUTOMATION_EXTENSIONS_COMPLETED",
        message="Automation extensions plan completed and ready for implementation.",
        payload={"human_review_required": True},
    )
