import asyncio

from fastapi import HTTPException

from service.config import settings
from service.storage.bots_repo import BotsRepository
from service.supervisor.bot_registry import BotRegistry
from service.supervisor.bot_types import run_heartbeat_bot
from service.supervisor.events import BotEventWriter


class BotRunner:
    def __init__(self, registry: BotRegistry, bots_repo: BotsRepository, event_writer: BotEventWriter):
        self.registry = registry
        self.bots_repo = bots_repo
        self.event_writer = event_writer
        self.tasks: dict[str, asyncio.Task] = {}

    async def start_bot(self, bot_id: str) -> dict:
        bot = self.registry.get_bot(bot_id)
        if bot_id in self.tasks and not self.tasks[bot_id].done():
            raise HTTPException(status_code=409, detail="Bot is already running")
        if len([task for task in self.tasks.values() if not task.done()]) >= settings.BOT_RUNNER_MAX_BOTS:
            raise HTTPException(status_code=409, detail="Bot runner capacity reached")

        self.registry.transition(bot_id, "running", "STARTED")
        refreshed = self.registry.get_bot(bot_id)

        if refreshed["bot_type"] == "heartbeat":
            interval = int(refreshed["config"].get("interval_seconds", settings.BOT_HEARTBEAT_DEFAULT_SECONDS))
            task = asyncio.create_task(
                self._run_heartbeat(refreshed["bot_id"], refreshed["owner_client_id"], interval),
                name=f"bot-{bot_id}",
            )
        else:
            self.registry.transition(bot_id, "error", "ERROR")
            raise HTTPException(status_code=409, detail=f"Unsupported bot type '{refreshed['bot_type']}'")

        self.tasks[bot_id] = task
        return self.registry.get_bot(bot_id)

    async def _run_heartbeat(self, bot_id: str, owner_client_id: str, interval: int) -> None:
        try:
            await run_heartbeat_bot(bot_id, owner_client_id, interval, self.event_writer)
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
