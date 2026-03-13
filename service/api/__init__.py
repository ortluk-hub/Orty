from fastapi import FastAPI

from service.api.deps import get_runtime
from service.api.routes.chat import router as chat_router
from service.api.routes.health import router as health_router
from service.api.routes.ui import root_router as ui_root_router
from service.api.routes.ui import router as ui_router
from service.api.routes.v1_auth import router as v1_auth_router
from service.api.routes.v1_bots import router as v1_bots_router
from service.api.routes.v1_bug_reports import router as v1_bug_reports_router
from service.api.routes.v1_clients import router as v1_clients_router
from service.api.routes.v1_memory import router as v1_memory_router
from service.api.routes.v1_memory import compat_router as memory_sync_compat_router

def create_app() -> FastAPI:
    app = FastAPI(title='Orty AI Assistant')
    app.state.runtime = get_runtime()

    @app.on_event("startup")
    async def startup() -> None:
        app.state.runtime = getattr(app.state, "runtime", None) or get_runtime()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        runtime = getattr(app.state, "runtime", None)
        if runtime is not None:
            await runtime.bot_runner.shutdown()

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(v1_auth_router)
    app.include_router(v1_clients_router)
    app.include_router(v1_bug_reports_router)
    app.include_router(v1_memory_router)
    app.include_router(memory_sync_compat_router)
    app.include_router(v1_bots_router)

    app.include_router(ui_root_router)
    app.include_router(ui_router)
    return app


app = create_app()
