import asyncio

from fastapi import HTTPException

from service.config import settings
from service.memory import MemoryStore
from service.storage.bots_repo import BotsRepository
from service.supervisor.bot_registry import BotRegistry
from service.supervisor.bot_types import run_code_review_bot, run_heartbeat_bot
from service.supervisor.events import BotEventWriter


class BotRunner:
    def __init__(self, registry: BotRegistry, bots_repo: BotsRepository, event_writer: BotEventWriter, memory_store: MemoryStore):
        self.registry = registry
        self.bots_repo = bots_repo
        self.event_writer = event_writer
        self.memory_store = memory_store
        self.tasks: dict[str, asyncio.Task] = {}

    async def start_bot(self, bot_id: str) -> dict:
        bot = self.registry.get_bot(bot_id)
        if bot_id in self.tasks and not self.tasks[bot_id].done():
            raise HTTPException(status_code=409, detail="Bot is already running")
        if len([task for task in self.tasks.values() if not task.done()]) >= settings.BOT_RUNNER_MAX_BOTS:
            raise HTTPException(status_code=409, detail="Bot runner capacity reached")

        task = self._build_task(bot)

        self.registry.transition(bot_id, "running", "STARTED")
        self.tasks[bot_id] = task
        return self.registry.get_bot(bot_id)

    def _build_task(self, bot: dict) -> asyncio.Task:
        if bot["bot_type"] == "heartbeat":
            interval = self._parse_heartbeat_interval(bot)
            return asyncio.create_task(
                self._run_heartbeat(bot["bot_id"], bot["owner_client_id"], interval),
                name=f"bot-{bot['bot_id']}",
            )

        if bot["bot_type"] == "code_review":
            return asyncio.create_task(
                self._run_code_review(bot["bot_id"], bot["owner_client_id"], bot["config"]),
                name=f"bot-{bot['bot_id']}",
            )

        raise HTTPException(status_code=409, detail=f"Unsupported bot type '{bot['bot_type']}'")

    def _parse_heartbeat_interval(self, bot: dict) -> int:
        raw_interval = bot["config"].get("interval_seconds", settings.BOT_HEARTBEAT_DEFAULT_SECONDS)
        try:
            interval = int(raw_interval)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="interval_seconds must be a positive integer") from exc

        if interval <= 0:
            raise HTTPException(status_code=422, detail="interval_seconds must be greater than 0")
        return interval

    async def _run_heartbeat(self, bot_id: str, owner_client_id: str, interval: int) -> None:
        try:
            await run_heartbeat_bot(bot_id, owner_client_id, interval, self.event_writer)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            self.bots_repo.update_status(bot_id, "error")
            self.event_writer.emit(bot_id, owner_client_id, "ERROR", message=str(exc))

    async def _run_code_review(self, bot_id: str, owner_client_id: str, config: dict) -> None:
        try:
            await run_code_review_bot(bot_id, owner_client_id, config, self.memory_store, self.event_writer)
            self.bots_repo.update_status(bot_id, "stopped")
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            self.bots_repo.update_status(bot_id, "error")
            self.event_writer.emit(bot_id, owner_client_id, "ERROR", message=str(exc))

    async def stop_bot(self, bot_id: str, paused: bool = False) -> dict:
        bot = self.registry.get_bot(bot_id)
        status = "paused" if paused else "stopped"
        event = "PAUSED" if paused else "STOPPED"

        task = self.tasks.get(bot_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        if bot["status"] != status:
            self.registry.transition(bot_id, status, event)
        return self.registry.get_bot(bot_id)
