import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from service.memory import MemoryStore
from service.supervisor.events import BotEventWriter


ROADMAP_FALLBACK = [
    "Conversation lifecycle controls",
    "Safer, extensible tool contracts",
    "Automation + integration expansion",
]


def _extract_focus_areas(roadmap_text: str) -> list[str]:
    lines = [line.strip(" -\t") for line in roadmap_text.splitlines() if line.strip()]
    if not lines:
        return ROADMAP_FALLBACK
    focus = [line for line in lines if len(line) > 8]
    return focus[:5] if focus else ROADMAP_FALLBACK


def _build_proposals(focus_areas: list[str], memory_messages: list[dict[str, str]], max_items: int) -> list[dict]:
    memory_text = "\n".join(msg.get("content", "") for msg in memory_messages).lower()
    proposals: list[dict] = []

    for idx, area in enumerate(focus_areas[:max_items], start=1):
        keywords = {token.lower() for token in area.split() if len(token) > 4}
        mentions = sum(1 for token in keywords if token in memory_text)
        relevance = "high" if mentions >= 2 else "medium" if mentions == 1 else "baseline"

        proposals.append(
            {
                "proposal_id": f"proposal-{idx}",
                "title": f"Advance roadmap area: {area}",
                "summary": (
                    "Prepare a focused pull request with tests that advances this roadmap objective. "
                    "Use chat memory signals to prioritize concrete APIs and guardrails."
                ),
                "memory_relevance": relevance,
                "memory_mentions": mentions,
                "human_review_required": True,
            }
        )
    return proposals


async def _clone_repo(repository_url: str, branch: str | None) -> str:
    tmp_dir = tempfile.mkdtemp(prefix="orty-review-")
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd.extend(["--branch", branch])
    cmd.extend([repository_url, tmp_dir])

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("Repository clone timed out")

    if process.returncode != 0:
        raise RuntimeError(stderr.decode().strip() or "Failed to clone repository")
    return tmp_dir


async def run_code_review_bot(
    bot_id: str,
    owner_client_id: str,
    config: dict,
    memory_store: MemoryStore,
    event_writer: BotEventWriter,
) -> None:
    repository_url = str(config.get("repository_url") or ".")
    branch = str(config.get("branch")) if config.get("branch") else None
    conversation_id = config.get("conversation_id")
    history_limit = int(config.get("history_limit", 20))
    max_proposals = int(config.get("max_proposals", 3))
    roadmap_text = str(config.get("roadmap_text") or "")

    if history_limit <= 0:
        history_limit = 20
    if max_proposals <= 0:
        max_proposals = 3

    clone_dir: str | None = None
    try:
        event_writer.emit(
            bot_id=bot_id,
            owner_client_id=owner_client_id,
            event_type="REVIEW_STARTED",
            message="Code review bot started. Any generated PRs require human review before merge.",
            payload={"repository_url": repository_url, "branch": branch, "human_review_required": True},
        )

        clone_dir = await _clone_repo(repository_url, branch)
        event_writer.emit(
            bot_id=bot_id,
            owner_client_id=owner_client_id,
            event_type="REPO_CLONED",
            message=f"Cloned repository into temporary workspace: {clone_dir}",
            payload={"branch": branch, "human_review_required": True},
        )

        memory_messages: list[dict[str, str]] = []
        if conversation_id:
            memory_messages = memory_store.get_recent_messages(str(conversation_id), limit=history_limit)

        focus_areas = _extract_focus_areas(roadmap_text)
        proposals = _build_proposals(focus_areas, memory_messages, max_items=max_proposals)

        event_writer.emit(
            bot_id=bot_id,
            owner_client_id=owner_client_id,
            event_type="REVIEW_PROPOSAL",
            message="Generated roadmap-aligned change proposals. Human PR review is mandatory.",
            payload={
                "conversation_id": conversation_id,
                "considered_memory_messages": len(memory_messages),
                "proposals": proposals,
                "human_review_required": True,
            },
        )

        event_writer.emit(
            bot_id=bot_id,
            owner_client_id=owner_client_id,
            event_type="REVIEW_COMPLETED",
            message="Code review cycle completed. Awaiting human-reviewed pull requests.",
            payload={"human_review_required": True},
        )
    finally:
        if clone_dir:
            shutil.rmtree(Path(clone_dir), ignore_errors=True)
