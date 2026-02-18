from fastapi import APIRouter, Depends

from service.api.deps import clients_repo
from service.models.schemas import ClientCreateRequest, ClientCreateResponse, ClientSummaryResponse
from service.security import verify_secret

router = APIRouter(prefix='/v1/clients', tags=['v1-clients'])


@router.post('', response_model=ClientCreateResponse)
async def create_client(request: ClientCreateRequest):
    return clients_repo.create_client(name=request.name)


@router.get('', response_model=list[ClientSummaryResponse])
async def list_clients(_: str = Depends(verify_secret)):
    return clients_repo.list_clients()
