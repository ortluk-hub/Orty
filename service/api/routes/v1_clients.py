from fastapi import APIRouter, Depends, HTTPException, Request

from service.api.deps import ensure_primary_client, get_request_auth, get_runtime
from service.models.schemas import (
    ClientCreateRequest,
    ClientCreateResponse,
    ClientPreferencesUpdateRequest,
    ClientSummaryResponse,
)
from service.security import verify_secret

router = APIRouter(prefix='/v1/clients', tags=['v1-clients'])


@router.post('', response_model=ClientCreateResponse)
async def create_client(payload: ClientCreateRequest, request: Request, _: str = Depends(verify_secret)):
    return get_runtime(request).clients_repo.create_client(name=payload.name, preferences=payload.preferences)


@router.get('', response_model=list[ClientSummaryResponse])
async def list_clients(request: Request, _: str = Depends(verify_secret)):
    ensure_primary_client(request)
    return get_runtime(request).clients_repo.list_clients()


@router.get('/me', response_model=ClientSummaryResponse)
async def get_me(auth: dict = Depends(get_request_auth)):
    client = auth.get("client")
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch('/me/preferences', response_model=ClientSummaryResponse)
async def update_my_preferences(
    payload: ClientPreferencesUpdateRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    client_id = auth["client_id"]
    updated = get_runtime(request).clients_repo.update_preferences(client_id, payload.preferences)
    if not updated:
        raise HTTPException(status_code=404, detail="Client not found")
    return updated
