from fastapi import APIRouter, Depends, HTTPException, Query

from service.api.deps import get_request_auth, memory_records_repo, memory_summaries_repo
from service.models.schemas import (
    MemoryRecordCreateRequest,
    MemoryRecordResponse,
    MemoryRecordUpdateRequest,
    MemorySummaryCreateRequest,
    MemorySummaryResponse,
)

router = APIRouter(prefix='/v1/memory', tags=['v1-memory'])


def _authorize_record_access(record: dict, auth: dict) -> None:
    if bool(auth.get('is_admin')):
        return
    requester_client_id = auth['client_id']
    if record['client_id'] != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')


def _model_updates(payload: MemoryRecordUpdateRequest) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)
    return payload.dict(exclude_unset=True)


@router.post('/records', response_model=MemoryRecordResponse)
async def create_memory_record(
    request: MemoryRecordCreateRequest,
    auth: dict = Depends(get_request_auth),
):
    is_admin = bool(auth.get('is_admin'))
    requester_client_id = auth['client_id']

    target_client_id = request.client_id or requester_client_id
    if not is_admin and target_client_id != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    record = memory_records_repo.create_record(
        client_id=target_client_id,
        memory_type=request.memory_type,
        content=request.content,
        summary=request.summary,
        tags=request.tags,
        importance=request.importance,
        source=request.source,
    )
    return MemoryRecordResponse(**record)


@router.get('/records', response_model=list[MemoryRecordResponse])
async def list_memory_records(
    auth: dict = Depends(get_request_auth),
    client_id: str | None = Query(default=None),
    memory_type: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    is_admin = bool(auth.get('is_admin'))
    requester_client_id = auth['client_id']

    target_client_id = client_id or requester_client_id
    if not is_admin and target_client_id != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    rows = memory_records_repo.list_records(
        client_id=target_client_id,
        memory_type=memory_type,
        tag=tag,
        source=source,
        limit=limit,
    )
    return [MemoryRecordResponse(**row) for row in rows]


@router.get('/records/{record_id}', response_model=MemoryRecordResponse)
async def get_memory_record(record_id: str, auth: dict = Depends(get_request_auth)):
    record = memory_records_repo.get_active_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail='Memory record not found')
    _authorize_record_access(record, auth)
    return MemoryRecordResponse(**record)


@router.patch('/records/{record_id}', response_model=MemoryRecordResponse)
async def update_memory_record(
    record_id: str,
    request: MemoryRecordUpdateRequest,
    auth: dict = Depends(get_request_auth),
):
    existing = memory_records_repo.get_active_record(record_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Memory record not found')
    _authorize_record_access(existing, auth)

    updates = _model_updates(request)
    updated = memory_records_repo.update_record(record_id, **updates)
    if not updated:
        raise HTTPException(status_code=404, detail='Memory record not found')
    return MemoryRecordResponse(**updated)


@router.delete('/records/{record_id}', response_model=dict)
async def delete_memory_record(record_id: str, auth: dict = Depends(get_request_auth)):
    existing = memory_records_repo.get_active_record(record_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Memory record not found')
    _authorize_record_access(existing, auth)

    deleted = memory_records_repo.soft_delete_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='Memory record not found')
    return {'deleted': True}


@router.post('/summaries', response_model=MemorySummaryResponse)
async def create_memory_summary(
    request: MemorySummaryCreateRequest,
    auth: dict = Depends(get_request_auth),
):
    is_admin = bool(auth.get('is_admin'))
    requester_client_id = auth['client_id']
    target_client_id = request.client_id or requester_client_id
    if not is_admin and target_client_id != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    summary = memory_summaries_repo.create_summary(
        client_id=target_client_id,
        conversation_id=request.conversation_id,
        context_version=request.context_version,
        summary=request.summary,
        source=request.source,
    )
    return MemorySummaryResponse(**summary)


@router.get('/summaries', response_model=list[MemorySummaryResponse])
async def list_memory_summaries(
    auth: dict = Depends(get_request_auth),
    client_id: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    is_admin = bool(auth.get('is_admin'))
    requester_client_id = auth['client_id']
    target_client_id = client_id or requester_client_id
    if not is_admin and target_client_id != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    rows = memory_summaries_repo.list_summaries(
        client_id=target_client_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return [MemorySummaryResponse(**row) for row in rows]


@router.get('/summaries/latest', response_model=MemorySummaryResponse)
async def get_latest_memory_summary(
    conversation_id: str = Query(..., min_length=1, max_length=120),
    auth: dict = Depends(get_request_auth),
    client_id: str | None = Query(default=None),
):
    is_admin = bool(auth.get('is_admin'))
    requester_client_id = auth['client_id']
    target_client_id = client_id or requester_client_id
    if not is_admin and target_client_id != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    row = memory_summaries_repo.get_latest_summary(
        client_id=target_client_id,
        conversation_id=conversation_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail='Memory summary not found')
    return MemorySummaryResponse(**row)


@router.get('/summaries/{summary_id}', response_model=MemorySummaryResponse)
async def get_memory_summary(summary_id: str, auth: dict = Depends(get_request_auth)):
    row = memory_summaries_repo.get_summary(summary_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Memory summary not found')
    if not bool(auth.get('is_admin')) and row['client_id'] != auth['client_id']:
        raise HTTPException(status_code=403, detail='Forbidden')
    return MemorySummaryResponse(**row)
