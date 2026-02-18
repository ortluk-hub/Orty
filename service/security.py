from fastapi import Header, HTTPException

from service.config import settings
from service.storage.clients_repo import ClientsRepository
from service.storage.db import SQLiteDB


async def verify_secret(x_orty_secret: str = Header(...)):
    if x_orty_secret != settings.ORTY_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def verify_client_token(client_id: str, token: str, clients_repo: ClientsRepository | None = None) -> bool:
    repo = clients_repo or ClientsRepository(SQLiteDB())
    return repo.verify_client_token(client_id, token)
