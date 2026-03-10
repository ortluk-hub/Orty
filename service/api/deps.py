from fastapi import Header, HTTPException

from service.config import settings
from service.memory import MemoryStore
from service.storage.bot_events_repo import BotEventsRepository
from service.storage.bots_repo import BotsRepository
from service.storage.clients_repo import ClientsRepository
from service.storage.db import SQLiteDB
from service.storage.memory_records_repo import MemoryRecordsRepository
from service.storage.memory_summaries_repo import MemorySummariesRepository
from service.supervisor.bot_registry import BotRegistry
from service.supervisor.bot_runner import BotRunner
from service.supervisor.events import BotEventWriter

_db = SQLiteDB()
clients_repo = ClientsRepository(_db)
bots_repo = BotsRepository(_db)
memory_records_repo = MemoryRecordsRepository(_db)
memory_summaries_repo = MemorySummariesRepository(_db)
bot_events_repo = BotEventsRepository(_db)
event_writer = BotEventWriter(bot_events_repo)
bot_registry = BotRegistry(bots_repo, event_writer)
memory_store = MemoryStore(_db.db_path)
bot_runner = BotRunner(bot_registry, bots_repo, event_writer, memory_store)


def ensure_primary_client() -> dict:
    primary = clients_repo.get_primary_client()
    if primary:
        return primary
    created = clients_repo.create_client(
        name="Primary Root Client",
        preferences={"role": "root", "ui_default": True},
        is_primary=True,
    )
    return clients_repo.get_client(created["client_id"]) or created


def require_client_auth(
    x_orty_client_id: str = Header(...),
    x_orty_client_token: str = Header(...),
) -> str:
    if not clients_repo.verify_client_token(x_orty_client_id, x_orty_client_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_orty_client_id


def get_request_auth(
    x_orty_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_orty_client_id: str | None = Header(default=None),
    x_orty_client_token: str | None = Header(default=None),
) -> dict:
    if x_orty_secret and x_orty_secret == settings.ORTY_SHARED_SECRET:
        primary = ensure_primary_client()
        return {
            "is_admin": True,
            "auth_method": "admin-secret",
            "client_id": primary["client_id"],
            "client": primary,
        }
    if authorization:
        prefix = "bearer "
        if authorization.lower().startswith(prefix):
            access_token = authorization[len(prefix):].strip()
            client = clients_repo.verify_access_token(access_token)
            if client:
                return {
                    "is_admin": False,
                    "auth_method": "bearer",
                    "client_id": client["client_id"],
                    "client": client,
                }

    if settings.ALLOW_LEGACY_CLIENT_HEADERS and x_orty_client_id and x_orty_client_token:
        if clients_repo.verify_client_token(x_orty_client_id, x_orty_client_token):
            client = clients_repo.get_client(x_orty_client_id)
            return {
                "is_admin": False,
                "auth_method": "legacy-client-headers",
                "client_id": x_orty_client_id,
                "client": client,
            }
    raise HTTPException(status_code=401, detail="Unauthorized")


def ensure_bot_owned_or_admin(bot: dict, requester_client_id: str | None, is_admin: bool) -> None:
    if is_admin:
        return
    if requester_client_id != bot["owner_client_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
