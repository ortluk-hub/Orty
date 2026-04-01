from dataclasses import dataclass
import logging

from fastapi import Header, HTTPException, Request

from service.config import settings
from service.ai import AIService
from service.memory import MemoryStore
from service.storage.bot_events_repo import BotEventsRepository
from service.storage.bots_repo import BotsRepository
from service.storage.bug_reports_repo import BugReportsRepository
from service.storage.clients_repo import ClientsRepository
from service.storage.db import Database, build_database
from service.storage.memory_records_repo import MemoryRecordsRepository
from service.storage.memory_summaries_repo import MemorySummariesRepository
from service.supervisor.bot_registry import BotRegistry
from service.supervisor.bot_runner import BotRunner
from service.supervisor.events import BotEventWriter
from service.integrations.codey_client import CodeyClient
from service.integrations.bug_report_processor import BugReportProcessor


logger = logging.getLogger("orty.auth")


@dataclass
class RuntimeContainer:
    db: Database
    clients_repo: ClientsRepository
    bots_repo: BotsRepository
    bug_reports_repo: BugReportsRepository
    memory_records_repo: MemoryRecordsRepository
    memory_summaries_repo: MemorySummariesRepository
    bot_events_repo: BotEventsRepository
    event_writer: BotEventWriter
    bot_registry: BotRegistry
    memory_store: MemoryStore
    bot_runner: BotRunner
    ai_service: AIService
    codey_client: CodeyClient | None
    codey_bug_processor: BugReportProcessor | None


def build_runtime(db_path: str | None = None) -> RuntimeContainer:
    db = build_database(db_path)
    clients_repo = ClientsRepository(db)
    bots_repo = BotsRepository(db)
    bug_reports_repo = BugReportsRepository(db)
    memory_records_repo = MemoryRecordsRepository(db)
    memory_summaries_repo = MemorySummariesRepository(db)
    bot_events_repo = BotEventsRepository(db)
    event_writer = BotEventWriter(bot_events_repo)
    bot_registry = BotRegistry(bots_repo, event_writer)
    memory_store = MemoryStore(db)
    bot_runner = BotRunner(bot_registry, bots_repo, event_writer, memory_store)
    # Initialize Codey integration if configured
    codey_client = None
    codey_bug_processor = None
    codey_url = settings.CODEY_URL if hasattr(settings, "CODEY_URL") else None
    if codey_url:
        codey_client = CodeyClient(
            base_url=codey_url,
            api_key=settings.CODEY_API_KEY if hasattr(settings, "CODEY_API_KEY") else None,
        )
        workspace_ref = settings.CODEY_ALFRED_WORKSPACE if hasattr(settings, "CODEY_ALFRED_WORKSPACE") else ""
        codey_bug_processor = BugReportProcessor(
            codey_client=codey_client,
            workspace_ref=workspace_ref,
            bug_reports_repo=bug_reports_repo,
            auto_approve_low_risk=True,  # Orty can auto-approve low-risk fixes
            notify_user_on_plan=True,    # Notify user of plans
            require_approval_for_high_risk=True,  # User approval for high-risk
        )

    ai_service = AIService(
        clients_repo=clients_repo,
        bots_repo=bots_repo,
        bug_reports_repo=bug_reports_repo,
        memory_records_repo=memory_records_repo,
        codey_client=codey_client,
        codey_bug_processor=codey_bug_processor,
    )

    return RuntimeContainer(
        db=db,
        clients_repo=clients_repo,
        bots_repo=bots_repo,
        bug_reports_repo=bug_reports_repo,
        memory_records_repo=memory_records_repo,
        memory_summaries_repo=memory_summaries_repo,
        bot_events_repo=bot_events_repo,
        event_writer=event_writer,
        bot_registry=bot_registry,
        memory_store=memory_store,
        bot_runner=bot_runner,
        ai_service=ai_service,
        codey_client=codey_client,
        codey_bug_processor=codey_bug_processor,
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
            client, bearer_reason = runtime.clients_repo.verify_access_token_with_reason(access_token)
            if client:
                # Check if client has admin status
                is_admin = runtime.clients_repo.is_admin(client["client_id"])
                return {
                    "is_admin": is_admin,
                    "auth_method": "bearer",
                    "client_id": client["client_id"],
                    "client": client,
                }
            logger.info("auth_diag bearer_rejected reason=%s", bearer_reason)

    if settings.ALLOW_LEGACY_CLIENT_HEADERS and x_orty_client_id and x_orty_client_token:
        if runtime.clients_repo.verify_client_token(x_orty_client_id, x_orty_client_token):
            client = runtime.clients_repo.get_client(x_orty_client_id)
            if client:
                # Check if client has admin status
                is_admin = runtime.clients_repo.is_admin(client["client_id"])
                return {
                    "is_admin": is_admin,
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
