from fastapi import HTTPException

from service.storage.bots_repo import BotsRepository
from service.supervisor.events import BotEventWriter


VALID_TRANSITIONS = {
    "created": {"running", "paused", "stopped"},
    "running": {"paused", "stopped"},
    "paused": {"running", "stopped"},
    "stopped": {"running", "paused"},
    "error": {"stopped", "running"},
}


class BotRegistry:
    def __init__(self, bots_repo: BotsRepository, event_writer: BotEventWriter):
        self.bots_repo = bots_repo
        self.event_writer = event_writer

    def create_bot(self, owner_client_id: str, bot_type: str, config: dict) -> dict:
        return self.bots_repo.create_bot(owner_client_id, bot_type, config)

    def get_bot(self, bot_id: str) -> dict:
        bot = self.bots_repo.get_bot(bot_id)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        return bot

    def transition(self, bot_id: str, to_status: str, event_type: str) -> dict:
        bot = self.get_bot(bot_id)
        current = bot["status"]
        if to_status not in VALID_TRANSITIONS.get(current, set()):
            raise HTTPException(status_code=409, detail=f"Invalid transition from {current} to {to_status}")
        updated = self.bots_repo.update_status(bot_id, to_status)
        self.event_writer.emit(bot_id, bot["owner_client_id"], event_type=event_type)
        return updated
