from fastapi import Header, HTTPException

from service.config import settings


async def verify_secret(x_orty_secret: str = Header(...)):
    if x_orty_secret != settings.ORTY_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def verify_client_token(client_id: str, token: str, clients_repo=None) -> bool:
    if clients_repo is None:
        from service.api.deps import get_runtime

        repo = get_runtime().clients_repo
    else:
        repo = clients_repo
    return repo.verify_client_token(client_id, token)
