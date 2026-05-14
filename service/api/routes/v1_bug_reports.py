from fastapi import APIRouter, Depends, HTTPException, Query, Request

from service.api.deps import get_request_auth, get_runtime
from service.models.schemas import (
    BugReportCreateRequest,
    BugReportCreateResponse,
    BugReportRecordResponse,
)

router = APIRouter(prefix="/v1/bug-reports", tags=["v1-bug-reports"])
BUG_REPORT_SOURCE = "alfred-bug-report"


def _resolve_target_client_id(payload: BugReportCreateRequest, auth: dict) -> str:
    requester_client_id = auth["client_id"]
    requested_client_id = payload.client_id
    if requested_client_id and requested_client_id != requester_client_id and not bool(auth.get("is_admin")):
        raise HTTPException(status_code=403, detail="Forbidden")
    return requested_client_id or requester_client_id


@router.post("", response_model=BugReportCreateResponse)
async def create_bug_report(
    payload: BugReportCreateRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    runtime = get_runtime(request)
    record = runtime.bug_reports_repo.create_report(
        client_id=_resolve_target_client_id(payload, auth),
        client=payload.client,
        source=BUG_REPORT_SOURCE,
        title=payload.title,
        summary=payload.summary,
        details=payload.details,
        metadata=payload.metadata,
        source_created_at=payload.createdAt,
    )

    # Submit to Codey for automated processing
    codey_processor = runtime.codey_bug_processor
    if codey_processor:
        codey_task = codey_processor.submit_to_codey(
            report_id=record["report_id"],
            title=record["title"],
            summary=record["summary"],
            details=record["details"],
            client_id=record["client_id"],
            metadata=record.get("metadata"),
            source_created_at=record.get("createdAt"),
        )
        if codey_task:
            record["codey_task_id"] = codey_task.get("task_id")
            record["codey_status"] = codey_task.get("status", "queued")

    return BugReportCreateResponse(status="ok", report_id=record["report_id"])


@router.get("", response_model=list[BugReportRecordResponse])
async def list_bug_reports(
    request: Request,
    auth: dict = Depends(get_request_auth),
    client_id: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    requester_client_id = auth["client_id"]
    is_admin = bool(auth.get("is_admin"))

    # Admins can view all bugs or filter by specific client_id
    # Non-admins can only view their own bugs
    if is_admin:
        target_client_id = client_id  # Can be None (all clients) or specific client_id
    else:
        target_client_id = client_id or requester_client_id
        if target_client_id != requester_client_id:
            raise HTTPException(status_code=403, detail="Forbidden")

    rows = get_runtime(request).bug_reports_repo.list_reports(
        client_id=target_client_id,
        source=source,
        limit=limit,
    )
    return [BugReportRecordResponse(**row) for row in rows]
