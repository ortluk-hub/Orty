"""Conversational bug report API endpoints.

These endpoints allow Orty to query and manipulate bug reports
as part of natural conversation, like tool calls.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from service.api.deps import get_request_auth, get_runtime
from service.integrations.bug_report_tools import BugReportTools
from service.storage.bug_reports_repo import BugReportsRepository


router = APIRouter(prefix="/v1/bugs", tags=["v1-bugs-conversational"])


def get_bug_tools(request: Request) -> BugReportTools:
    """Get bug tools instance from runtime."""
    runtime = get_runtime(request)
    return BugReportTools(
        bug_reports_repo=runtime.bug_reports_repo,
        codey_processor=runtime.codey_bug_processor,
    )


@router.get("/list")
async def list_bugs(
    request: Request,
    status: str | None = Query(default=None, description="Filter by status"),
    source: str | None = Query(default=None, description="Filter by source"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
    auth: dict = Depends(get_request_auth),
):
    """List bug reports - conversational interface.

    Example conversation:
    User: "Show me all pending bugs"
    → GET /v1/bugs/list?status=pending

    User: "What bugs did Alfred report?"
    → GET /v1/bugs/list?source=alfred-bug-report
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    bugs = bug_tools.list_bug_reports(status=status, source=source, limit=limit)

    return {
        "bugs": bugs,
        "count": len(bugs),
        "filters": {
            "status": status,
            "source": source,
            "limit": limit,
        },
    }


@router.get("/{report_id}")
async def get_bug(
    report_id: str,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    """Get bug report details - conversational interface.

    Example conversation:
    User: "What's the status of bug 93c4c855?"
    → GET /v1/bugs/93c4c855

    User: "Show me details for bug abc12345"
    → GET /v1/bugs/abc12345
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    bug = bug_tools.get_bug_report(report_id)

    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")

    return {
        "bug": bug,
        "conversation_context": {
            "can_approve": bool(bug.get("codey_task_id") and bug.get("codey_status") == "planned"),
            "can_forward": not bool(bug.get("codey_task_id")),
        },
    }


@router.get("/{report_id}/status")
async def get_bug_status(
    report_id: str,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    """Get bug status only - quick conversational check.

    Example conversation:
    User: "Is bug 93c4c855 fixed yet?"
    → GET /v1/bugs/93c4c855/status
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    status = bug_tools.get_bug_status(report_id)

    if not status:
        raise HTTPException(status_code=404, detail="Bug not found")

    return status


@router.post("/submit")
async def submit_bug(
    request: Request,
    title: str = Query(..., description="Bug title"),
    summary: str = Query(..., description="Brief summary"),
    details: str = Query(..., description="Full details"),
    forward_to_codey: bool = Query(default=True, description="Forward to Codey automatically"),
    auth: dict = Depends(get_request_auth),
):
    """Submit a new bug from conversation.

    Example conversation:
    User: "Report a bug: the keyboard has too much spacing"
    → POST /v1/bugs/submit?title=Keyboard%20spacing&summary=...&details=...
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    bug = bug_tools.submit_bug_report(
        title=title,
        summary=summary,
        details=details,
        forward_to_codey=forward_to_codey,
    )

    if not bug:
        raise HTTPException(status_code=500, detail="Failed to create bug report")

    action_taken = "forwarded to Codey" if forward_to_codey and bug.get("codey_task_id") else "created"

    return {
        "bug": {
            "report_id": bug["report_id"][:8],
            "title": bug["title"],
            "status": bug.get("status"),
        },
        "action": action_taken,
        "codey_task_id": bug.get("codey_task_id", "")[:8] if bug.get("codey_task_id") else None,
    }


@router.post("/{report_id}/forward")
async def forward_to_codey(
    report_id: str,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    """Forward existing bug to Codey.

    Example conversation:
    User: "Send bug 93c4c855 to Codey for fixing"
    → POST /v1/bugs/93c4c855/forward
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    codey_task = bug_tools.forward_to_codey(report_id)

    if not codey_task:
        raise HTTPException(status_code=404, detail="Bug not found or Codey not configured")

    return {
        "report_id": report_id,
        "codey_task_id": codey_task.get("task_id", "")[:8],
        "status": codey_task.get("status"),
        "message": f"Bug {report_id[:8]} forwarded to Codey",
    }


@router.post("/{report_id}/approve")
async def approve_plan(
    report_id: str,
    request: Request,
    approved_by: str = Query(default="orty_supervisor", description="Approver identifier"),
    auth: dict = Depends(get_request_auth),
):
    """Approve Codey fix plan from conversation.

    Example conversation:
    User: "Approve the fix for bug 93c4c855"
    → POST /v1/bugs/93c4c855/approve
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    result = bug_tools.approve_codey_plan(report_id, approved_by=approved_by)

    if not result:
        raise HTTPException(status_code=404, detail="Bug not found or no Codey task")

    if not result.get("approved"):
        raise HTTPException(status_code=500, detail="Approval failed")

    return {
        "report_id": report_id,
        "codey_task_id": result.get("codey_task_id", "")[:8],
        "approved": True,
        "status": result.get("status"),
        "message": f"Plan approved for bug {report_id[:8]}",
    }


@router.post("/{report_id}/reject")
async def reject_plan(
    report_id: str,
    request: Request,
    reason: str = Query(default="Rejected by Orty", description="Rejection reason"),
    auth: dict = Depends(get_request_auth),
):
    """Reject Codey fix plan from conversation.

    Example conversation:
    User: "Reject the fix for bug 93c4c855 - it's too risky"
    → POST /v1/bugs/93c4c855/reject?reason=too%20risky
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    result = bug_tools.reject_codey_plan(report_id, reason=reason)

    if not result:
        raise HTTPException(status_code=404, detail="Bug not found or no Codey task")

    if not result.get("rejected"):
        raise HTTPException(status_code=500, detail="Rejection failed")

    return {
        "report_id": report_id,
        "rejected": True,
        "reason": reason,
        "message": f"Plan rejected for bug {report_id[:8]}",
    }


@router.get("/stats/summary")
async def get_bug_stats(
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    """Get bug statistics for conversation.

    Example conversation:
    User: "How many bugs do we have?"
    → GET /v1/bugs/stats/summary
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    stats = bug_tools.get_bug_stats()

    return {
        "total_bugs": stats["total"],
        "by_status": stats["by_status"],
        "by_codey_status": stats["by_codey_status"],
        "summary": f"{stats['total']} bugs total: {stats['by_status'].get('pending', 0)} pending, {stats['by_status'].get('planned', 0)} planned, {stats['by_status'].get('fixed_verified', 0)} verified",
    }


@router.get("/search")
async def search_bugs(
    request: Request,
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=20, ge=1, le=50, description="Maximum results"),
    auth: dict = Depends(get_request_auth),
):
    """Search bugs from conversation.

    Example conversation:
    User: "Find bugs about keyboard issues"
    → GET /v1/bugs/search?q=keyboard
    """
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    bug_tools = get_bug_tools(request)
    bugs = bug_tools.search_bugs(query=q, limit=limit)

    return {
        "query": q,
        "bugs": bugs,
        "count": len(bugs),
    }
