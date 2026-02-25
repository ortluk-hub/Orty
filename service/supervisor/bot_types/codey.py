from service.memory import MemoryStore
from service.supervisor.events import BotEventWriter


DEFAULT_MODES = [
    "conversation",
    "architecture",
    "code_generation",
    "code_review",
    "debugging",
]

MODE_PROMPTS = {
    "conversation": (
        "You are in conversation mode. Clarify goals, ask focused follow-ups, "
        "and summarize decisions before acting."
    ),
    "architecture": (
        "You are in architecture mode. Propose modular system designs, "
        "explicit interfaces, trade-offs, and rollout steps."
    ),
    "code_generation": (
        "You are in code generation mode. Produce implementation-ready code, "
        "tests, and concise rationale with secure defaults."
    ),
    "code_review": (
        "You are in code review mode. Audit correctness, security, and maintainability, "
        "then provide actionable, prioritized fixes."
    ),
    "debugging": (
        "You are in debugging mode. Reproduce issues, isolate root cause, and propose "
        "minimal-risk patches with validation commands."
    ),
}


BEST_PRACTICES_SYSTEM_PROMPT = (
    "You are Codey, a senior software engineering agent. "
    "Prioritize safety, reproducibility, and deterministic outputs. "
    "Always explain assumptions, propose tests, and avoid hidden side effects. "
    "All shell commands must execute inside a dedicated sandboxed Docker workspace. "
    "Internet access is restricted to data retrieval and GitHub interactions."
)

INTENT_RESOLVER_SYSTEM_PROMPT = (
    "You are Codey's intent resolver. Classify user intent and select exactly one mode from: "
    "conversation, architecture, code_generation, code_review, debugging."
)


def _normalized_modes(raw_modes: list[str] | str | None) -> list[str]:
    if not raw_modes:
        return DEFAULT_MODES

    if isinstance(raw_modes, str):
        raw_modes = [raw_modes]

    normalized: list[str] = []
    seen: set[str] = set()
    for mode in raw_modes:
        candidate = str(mode).strip().lower().replace(" ", "_")
        if not candidate or candidate in seen or candidate not in MODE_PROMPTS:
            continue
        seen.add(candidate)
        normalized.append(candidate)

    return normalized if normalized else DEFAULT_MODES


def _codey_spec(config: dict, modes: list[str]) -> dict:
    return {
        "working_title": str(config.get("working_title") or "Codey"),
        "intent_resolver": {
            "provider": "ollama",
            "model": str(config.get("intent_model") or "gwen3:0.6b"),
            "role": "Intent classification and mode routing",
        },
        "main_llm": {
            "provider": "ollama",
            "model": str(config.get("main_model") or "qwen3-coder:480b"),
            "hosting": "cloud",
        },
        "fallback_llm": {
            "provider": "ollama",
            "model": str(config.get("fallback_model") or "qwen2.5:1.5b"),
            "hosting": "local",
            "trigger": "Primary model unavailable, timeout, or budget guardrail",
        },
        "memory": {
            "engine": "alembic",
            "strategy": "Store condensed conversation context, tool outputs, and mode decisions",
        },
        "runtime_sandbox": {
            "executor": "docker",
            "policy": "All development tools and shell commands execute inside isolated per-task container",
            "internet_access": {
                "allow_github": True,
                "allow_data_retrieval": True,
                "deny_other_domains_by_default": True,
            },
            "allowed_network": ["github.com", "api.github.com"],
        },
        "tooling": {
            "supports_git": True,
            "supports_terminal": True,
            "supports_tests": True,
            "supports_linters": True,
        },
        "system_prompts": {
            "high_level": BEST_PRACTICES_SYSTEM_PROMPT,
            "intent_resolver": INTENT_RESOLVER_SYSTEM_PROMPT,
            "mode_prompts": {mode: MODE_PROMPTS[mode] for mode in modes},
        },
        "implementation_notes": [
            "Start one sandbox container per task/session and mount only workspace paths.",
            "Run git operations from the sandboxed container workspace.",
            "Persist summaries and tool traces through Alembic-backed memory migrations.",
        ],
        "human_review_required": True,
    }


async def run_codey_bot(
    bot_id: str,
    owner_client_id: str,
    config: dict,
    memory_store: MemoryStore,
    event_writer: BotEventWriter,
) -> None:
    del memory_store

    modes = _normalized_modes(config.get("modes"))
    spec = _codey_spec(config, modes)

    event_writer.emit(
        bot_id=bot_id,
        owner_client_id=owner_client_id,
        event_type="CODEY_PLANNING_STARTED",
        message="Codey planning started with intent resolver and multi-model routing.",
        payload={"working_title": spec["working_title"], "modes": modes},
    )

    event_writer.emit(
        bot_id=bot_id,
        owner_client_id=owner_client_id,
        event_type="CODEY_ARCHITECTURE_DRAFTED",
        message="Drafted Codey architecture with sandboxed Docker execution and restricted network policy.",
        payload=spec,
    )

    event_writer.emit(
        bot_id=bot_id,
        owner_client_id=owner_client_id,
        event_type="CODEY_COMPLETED",
        message="Codey plan completed; ready for implementation behind human review.",
        payload={"human_review_required": True},
    )
