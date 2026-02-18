from fastapi import Header, HTTPException

from service.config import settings
from service.security import verify_client_token
from service.storage.bot_events_repo import BotEventsRepository
from service.storage.bots_repo import BotsRepository
from service.storage.clients_repo import ClientsRepository
from service.storage.db import SQLiteDB
from service.supervisor.bot_registry import BotRegistry
from service.supervisor.bot_runner import BotRunner
from service.supervisor.events import BotEventWriter

_db = SQLiteDB()
clients_repo = ClientsRepository(_db)
bots_repo = BotsRepository(_db)
bot_events_repo = BotEventsRepository(_db)
event_writer = BotEventWriter(bot_events_repo)
bot_registry = BotRegistry(bots_repo, event_writer)
bot_runner = BotRunner(bot_registry, bots_repo, event_writer)


def require_client_auth(
    x_orty_client_id: str = Header(...),
    x_orty_client_token: str = Header(...),
) -> str:
    if not verify_client_token(x_orty_client_id, x_orty_client_token, clients_repo=clients_repo):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_orty_client_id


def get_request_auth(
    x_orty_secret: str | None = Header(default=None),
    x_orty_client_id: str | None = Header(default=None),
    x_orty_client_token: str | None = Header(default=None),
) -> dict:
    if x_orty_secret and x_orty_secret == settings.ORTY_SHARED_SECRET:
        return {"is_admin": True, "client_id": None}
    if x_orty_client_id and x_orty_client_token:
        if verify_client_token(x_orty_client_id, x_orty_client_token, clients_repo=clients_repo):
            return {"is_admin": False, "client_id": x_orty_client_id}
    raise HTTPException(status_code=401, detail="Unauthorized")


def ensure_bot_owned_or_admin(bot: dict, requester_client_id: str | None, is_admin: bool) -> None:
    if is_admin:
        return
    if requester_client_id != bot["owner_client_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
