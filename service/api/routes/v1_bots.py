from fastapi import APIRouter, Depends, HTTPException, Query

from service.api.deps import (
    bot_events_repo,
    bot_registry,
    bot_runner,
    ensure_bot_owned_or_admin,
    get_request_auth,
)
from service.models.schemas import BotCreateRequest, BotCreateResponse, BotEventResponse, BotStatusResponse

router = APIRouter(prefix='/v1/bots', tags=['v1-bots'])


@router.post('', response_model=BotCreateResponse)
async def create_bot(request: BotCreateRequest, auth: dict = Depends(get_request_auth)):
    if auth["is_admin"]:
        if not request.owner_client_id:
            raise HTTPException(status_code=400, detail='owner_client_id is required for admin requests')
        owner_client_id = request.owner_client_id
    else:
        owner_client_id = auth["client_id"]
        if request.owner_client_id and request.owner_client_id != owner_client_id:
            raise HTTPException(status_code=403, detail='Forbidden')
    return bot_registry.create_bot(owner_client_id, request.bot_type, request.config)


@router.post('/{bot_id}/start', response_model=BotStatusResponse)
async def start_bot(bot_id: str, auth: dict = Depends(get_request_auth)):
    bot = bot_registry.get_bot(bot_id)
    ensure_bot_owned_or_admin(bot, auth["client_id"], auth["is_admin"])
    return await bot_runner.start_bot(bot_id)


@router.post('/{bot_id}/stop', response_model=BotStatusResponse)
async def stop_bot(bot_id: str, auth: dict = Depends(get_request_auth)):
    bot = bot_registry.get_bot(bot_id)
    ensure_bot_owned_or_admin(bot, auth["client_id"], auth["is_admin"])
    return await bot_runner.stop_bot(bot_id, paused=False)


@router.post('/{bot_id}/pause', response_model=BotStatusResponse)
async def pause_bot(bot_id: str, auth: dict = Depends(get_request_auth)):
    bot = bot_registry.get_bot(bot_id)
    ensure_bot_owned_or_admin(bot, auth["client_id"], auth["is_admin"])
    return await bot_runner.stop_bot(bot_id, paused=True)


@router.get('/{bot_id}', response_model=BotStatusResponse)
async def get_bot_status(bot_id: str, auth: dict = Depends(get_request_auth)):
    bot = bot_registry.get_bot(bot_id)
    ensure_bot_owned_or_admin(bot, auth["client_id"], auth["is_admin"])
    return bot


@router.get('/{bot_id}/events', response_model=list[BotEventResponse])
async def get_bot_events(
    bot_id: str,
    limit: int = Query(default=100, le=1000),
    auth: dict = Depends(get_request_auth),
):
    bot = bot_registry.get_bot(bot_id)
    ensure_bot_owned_or_admin(bot, auth["client_id"], auth["is_admin"])
    return bot_events_repo.list_events(bot_id, limit=limit)
