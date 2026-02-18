from fastapi import FastAPI

from service.api.routes.chat import router as chat_router
from service.api.routes.health import router as health_router
from service.api.routes.v1_bots import router as v1_bots_router
from service.api.routes.v1_clients import router as v1_clients_router

app = FastAPI(title='Orty AI Assistant')
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(v1_clients_router)
app.include_router(v1_bots_router)
