from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from service.config import settings
from service.ai import AIService
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


@dataclass
class RuntimeContainer:
    db: SQLiteDB
    clients_repo: ClientsRepository
    bots_repo: BotsRepository
    memory_records_repo: MemoryRecordsRepository
    memory_summaries_repo: MemorySummariesRepository
    bot_events_repo: BotEventsRepository
    event_writer: BotEventWriter
    bot_registry: BotRegistry
    memory_store: MemoryStore
    bot_runner: BotRunner
    ai_service: AIService


def build_runtime(db_path: str | None = None) -> RuntimeContainer:
    db = SQLiteDB(db_path)
    clients_repo = ClientsRepository(db)
    bots_repo = BotsRepository(db)
    memory_records_repo = MemoryRecordsRepository(db)
    memory_summaries_repo = MemorySummariesRepository(db)
    bot_events_repo = BotEventsRepository(db)
    event_writer = BotEventWriter(bot_events_repo)
    bot_registry = BotRegistry(bots_repo, event_writer)
    memory_store = MemoryStore(db.db_path)
    bot_runner = BotRunner(bot_registry, bots_repo, event_writer, memory_store)
    ai_service = AIService()
    return RuntimeContainer(
        db=db,
        clients_repo=clients_repo,
        bots_repo=bots_repo,
        memory_records_repo=memory_records_repo,
        memory_summaries_repo=memory_summaries_repo,
        bot_events_repo=bot_events_repo,
        event_writer=event_writer,
        bot_registry=bot_registry,
        memory_store=memory_store,
        bot_runner=bot_runner,
        ai_service=ai_service,
    )


_runtime = build_runtime()


def get_runtime(request: Request | None = None) -> RuntimeContainer:
    if request is not None:
        runtime = getattr(request.app.state, "runtime", None)
        if runtime is not None:
            return runtime
    return _runtime


def reset_runtime(db_path: str | None = None) -> RuntimeContainer:
    global _runtime
    _runtime = build_runtime(db_path)
    return _runtime


def ensure_primary_client(request: Request | None = None) -> dict:
    runtime = get_runtime(request)
    primary = runtime.clients_repo.get_primary_client()
    if primary:
        return primary
    created = runtime.clients_repo.create_client(
        name="Primary Root Client",
        preferences={"role": "root", "ui_default": True},
        is_primary=True,
    )
    return runtime.clients_repo.get_client(created["client_id"]) or created


def require_client_auth(
    request: Request,
    x_orty_client_id: str = Header(...),
    x_orty_client_token: str = Header(...),
) -> str:
    runtime = get_runtime(request)
    if not runtime.clients_repo.verify_client_token(x_orty_client_id, x_orty_client_token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_orty_client_id


async def get_request_auth(
    request: Request,
    x_orty_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_orty_client_id: str | None = Header(default=None),
    x_orty_client_token: str | None = Header(default=None),
) -> dict:
    runtime = get_runtime(request)
    if x_orty_secret and x_orty_secret == settings.ORTY_SHARED_SECRET:
        primary = ensure_primary_client(request)
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
            client = runtime.clients_repo.verify_access_token(access_token)
            if client:
                return {
                    "is_admin": False,
                    "auth_method": "bearer",
                    "client_id": client["client_id"],
                    "client": client,
                }

    if settings.ALLOW_LEGACY_CLIENT_HEADERS and x_orty_client_id and x_orty_client_token:
        if runtime.clients_repo.verify_client_token(x_orty_client_id, x_orty_client_token):
            client = runtime.clients_repo.get_client(x_orty_client_id)
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
