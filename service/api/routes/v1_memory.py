from fastapi import APIRouter, Depends, HTTPException, Query, Request

from service.api.deps import get_request_auth, get_runtime
from service.models.schemas import (
    MemoryRecordCreateRequest,
    MemoryRecordResponse,
    MemoryRecordUpdateRequest,
    MemorySummaryCreateRequest,
    MemorySummaryResponse,
    MemorySyncItem,
    MemorySyncRequest,
    MemorySyncResponse,
)

router = APIRouter(prefix='/v1/memory', tags=['v1-memory'])
compat_router = APIRouter(prefix='/memory', tags=['memory-sync'])
SYNC_SOURCE = "alfred-sync"


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


def _sync_request_payload(payload: MemorySyncRequest) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload.dict()


def _resolve_target_client_id(payload: MemorySyncRequest, auth: dict) -> str:
    requester_client_id = auth["client_id"]
    requested_client_id = payload.client_id
    if requested_client_id and requested_client_id != requester_client_id and not bool(auth.get("is_admin")):
        raise HTTPException(status_code=403, detail="Forbidden")
    return requested_client_id or requester_client_id


def _record_to_sync_item(record: dict) -> MemorySyncItem:
    created_at_ms = record.get("source_created_at") or _iso_to_epoch_ms(record["created_at"])
    updated_at_ms = record.get("source_updated_at") or _iso_to_epoch_ms(record["updated_at"])
    return MemorySyncItem(
        key=record["external_key"],
        category=record["memory_type"],
        summary=record["summary"] or record["content"],
        sourceText=record["content"],
        createdAt=created_at_ms,
        updatedAt=updated_at_ms,
        isPinned=bool(record.get("is_pinned")),
        expiresAt=record.get("expires_at"),
    )


def _iso_to_epoch_ms(value: str) -> int:
    from datetime import datetime

    return int(datetime.fromisoformat(value).timestamp() * 1000)


def _sync_memories_impl(payload: MemorySyncRequest, auth: dict, runtime) -> MemorySyncResponse:
    target_client_id = _resolve_target_client_id(payload, auth)
    request_payload = _sync_request_payload(payload)
    memories = request_payload.get("memories", [])

    keep_keys: list[str] = []
    for item in memories:
        key = item["key"]
        keep_keys.append(key)
        runtime.memory_records_repo.upsert_sync_record(
            client_id=target_client_id,
            external_key=key,
            memory_type=item["category"],
            content=item["sourceText"],
            summary=item["summary"],
            tags=[],
            importance=1.0 if item.get("isPinned") else 0.75,
            source=SYNC_SOURCE,
            is_pinned=bool(item.get("isPinned")),
            expires_at=item.get("expiresAt"),
            source_created_at=item.get("createdAt"),
            source_updated_at=item.get("updatedAt"),
        )

    runtime.memory_records_repo.soft_delete_sync_records_missing_keys(
        client_id=target_client_id,
        source=SYNC_SOURCE,
        keep_external_keys=keep_keys,
    )
    canonical = runtime.memory_records_repo.list_active_sync_records(
        client_id=target_client_id,
        source=SYNC_SOURCE,
        limit=None,
    )
    return MemorySyncResponse(
        status="ok",
        syncedCount=len(canonical),
        memories=[_record_to_sync_item(record) for record in canonical if record.get("external_key")],
    )


@router.post('/records', response_model=MemoryRecordResponse)
async def create_memory_record(
    payload: MemoryRecordCreateRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    runtime = get_runtime(request)
    is_admin = bool(auth.get('is_admin'))
    requester_client_id = auth['client_id']

    target_client_id = payload.client_id or requester_client_id
    if not is_admin and target_client_id != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    record = runtime.memory_records_repo.create_record(
        client_id=target_client_id,
        memory_type=payload.memory_type,
        content=payload.content,
        summary=payload.summary,
        tags=payload.tags,
        importance=payload.importance,
        source=payload.source,
        external_key=payload.external_key,
        is_pinned=payload.is_pinned,
        expires_at=payload.expires_at,
    )
    return MemoryRecordResponse(**record)


@router.get('/records', response_model=list[MemoryRecordResponse])
async def list_memory_records(
    request: Request,
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

    rows = get_runtime(request).memory_records_repo.list_records(
        client_id=target_client_id,
        memory_type=memory_type,
        tag=tag,
        source=source,
        limit=limit,
    )
    return [MemoryRecordResponse(**row) for row in rows]


@router.get('/records/{record_id}', response_model=MemoryRecordResponse)
async def get_memory_record(record_id: str, request: Request, auth: dict = Depends(get_request_auth)):
    record = get_runtime(request).memory_records_repo.get_active_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail='Memory record not found')
    _authorize_record_access(record, auth)
    return MemoryRecordResponse(**record)


@router.patch('/records/{record_id}', response_model=MemoryRecordResponse)
async def update_memory_record(
    record_id: str,
    payload: MemoryRecordUpdateRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    runtime = get_runtime(request)
    existing = runtime.memory_records_repo.get_active_record(record_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Memory record not found')
    _authorize_record_access(existing, auth)

    updates = _model_updates(payload)
    updated = runtime.memory_records_repo.update_record(record_id, **updates)
    if not updated:
        raise HTTPException(status_code=404, detail='Memory record not found')
    return MemoryRecordResponse(**updated)


@router.delete('/records/{record_id}', response_model=dict)
async def delete_memory_record(record_id: str, request: Request, auth: dict = Depends(get_request_auth)):
    runtime = get_runtime(request)
    existing = runtime.memory_records_repo.get_active_record(record_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Memory record not found')
    _authorize_record_access(existing, auth)

    deleted = runtime.memory_records_repo.soft_delete_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='Memory record not found')
    return {'deleted': True}


@router.post('/sync', response_model=MemorySyncResponse)
async def sync_memory_records_v1(
    payload: MemorySyncRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    return _sync_memories_impl(payload, auth, get_runtime(request))


@compat_router.post('/sync', response_model=MemorySyncResponse)
async def sync_memory_records_compat(
    payload: MemorySyncRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    return _sync_memories_impl(payload, auth, get_runtime(request))


@router.post('/summaries', response_model=MemorySummaryResponse)
async def create_memory_summary(
    payload: MemorySummaryCreateRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    runtime = get_runtime(request)
    is_admin = bool(auth.get('is_admin'))
    requester_client_id = auth['client_id']
    target_client_id = payload.client_id or requester_client_id
    if not is_admin and target_client_id != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    summary = runtime.memory_summaries_repo.create_summary(
        client_id=target_client_id,
        conversation_id=payload.conversation_id,
        context_version=payload.context_version,
        summary=payload.summary,
        source=payload.source,
    )
    return MemorySummaryResponse(**summary)


@router.get('/summaries', response_model=list[MemorySummaryResponse])
async def list_memory_summaries(
    request: Request,
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

    rows = get_runtime(request).memory_summaries_repo.list_summaries(
        client_id=target_client_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return [MemorySummaryResponse(**row) for row in rows]


@router.get('/summaries/latest', response_model=MemorySummaryResponse)
async def get_latest_memory_summary(
    request: Request,
    conversation_id: str = Query(..., min_length=1, max_length=120),
    auth: dict = Depends(get_request_auth),
    client_id: str | None = Query(default=None),
):
    is_admin = bool(auth.get('is_admin'))
    requester_client_id = auth['client_id']
    target_client_id = client_id or requester_client_id
    if not is_admin and target_client_id != requester_client_id:
        raise HTTPException(status_code=403, detail='Forbidden')

    row = get_runtime(request).memory_summaries_repo.get_latest_summary(
        client_id=target_client_id,
        conversation_id=conversation_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail='Memory summary not found')
    return MemorySummaryResponse(**row)


@router.get('/summaries/{summary_id}', response_model=MemorySummaryResponse)
async def get_memory_summary(summary_id: str, request: Request, auth: dict = Depends(get_request_auth)):
    row = get_runtime(request).memory_summaries_repo.get_summary(summary_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Memory summary not found')
    if not bool(auth.get('is_admin')) and row['client_id'] != auth['client_id']:
        raise HTTPException(status_code=403, detail='Forbidden')
    return MemorySummaryResponse(**row)
