from service.storage.bot_events_repo import BotEventsRepository


class BotEventWriter:
    def __init__(self, events_repo: BotEventsRepository):
        self.events_repo = events_repo

    def emit(
        self,
        bot_id: str,
        owner_client_id: str,
        event_type: str,
        message: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        return self.events_repo.add_event(bot_id, owner_client_id, event_type, message, payload)
