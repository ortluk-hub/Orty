from fastapi import APIRouter, Depends, HTTPException, Request

from service.api.deps import ensure_primary_client, get_request_auth, get_runtime
from service.config import settings
from service.models.schemas import (
    ClientAccessTierUpdateRequest,
    ClientCreateRequest,
    ClientRegisterRequest,
    ClientCreateResponse,
    ClientPreferencesUpdateRequest,
    ClientPromotionApproveRequest,
    ClientPromotionListResponse,
    ClientPromotionRejectRequest,
    ClientPromotionRequest,
    ClientPromotionRequestResponse,
    ClientSummaryResponse,
)
from service.security import hash_token, verify_secret

router = APIRouter(prefix='/v1/clients', tags=['v1-clients'])


@router.post('', response_model=ClientCreateResponse)
async def create_client(payload: ClientCreateRequest, request: Request, _: str = Depends(verify_secret)):
    return get_runtime(request).clients_repo.create_client(name=payload.name, preferences=payload.preferences)


@router.post('/register', response_model=ClientCreateResponse)
async def register_alfred_client(payload: ClientRegisterRequest, request: Request):
    configured_client_key = (settings.ORTY_ALFRED_CLIENT_KEY or '').strip()
    if not configured_client_key:
        raise HTTPException(status_code=503, detail='Alfred client registration is not configured')
    if payload.client_key.strip() != configured_client_key:
        raise HTTPException(status_code=401, detail='Unauthorized')
    name = payload.name or 'Alfred Client'
    return get_runtime(request).clients_repo.register_alfred_client(name=name, preferences=payload.preferences)


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


@router.post('/me/disconnect', response_model=ClientSummaryResponse)
async def disconnect_me(
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    client_id = auth["client_id"]
    updated = get_runtime(request).clients_repo.revoke_client(client_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Client not found")
    return updated


@router.post('/me/promotion/request', response_model=ClientPromotionRequestResponse)
async def request_promotion(
    payload: ClientPromotionRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    """Submit a promotion request for admin status.
    
    Client must provide a hash of the admin secret to verify they have
    legitimate access to the secret (e.g., from documentation or setup).
    """
    client_id = auth["client_id"]
    runtime = get_runtime(request)
    
    # Check if already admin
    if runtime.clients_repo.is_admin(client_id):
        raise HTTPException(status_code=400, detail="Client already has admin status")
    
    # Check if request already exists
    existing = runtime.clients_repo.get_promotion_requests(status="pending")
    if any(r["client_id"] == client_id for r in existing):
        raise HTTPException(status_code=400, detail="Promotion request already pending")
    
    result = runtime.clients_repo.request_promotion(
        client_id=client_id,
        reason=payload.reason,
        admin_secret_hash=payload.admin_secret_hash,
    )
    
    if not result:
        raise HTTPException(status_code=401, detail="Invalid admin secret")
    
    return ClientPromotionRequestResponse(**result)


@router.get('/promotion/requests', response_model=ClientPromotionListResponse)
async def list_promotion_requests(
    request: Request,
    auth: dict = Depends(get_request_auth),
    status: str | None = "pending",
):
    """List promotion requests (admin only)."""
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    runtime = get_runtime(request)
    requests_list = runtime.clients_repo.get_promotion_requests(status=status)
    
    return ClientPromotionListResponse(
        requests=requests_list,
        total=len(requests_list),
    )


@router.post('/promotion/approve', response_model=ClientSummaryResponse)
async def approve_promotion(
    payload: ClientPromotionApproveRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    """Approve a promotion request (admin only)."""
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    runtime = get_runtime(request)
    reviewer_client_id = auth["client_id"]
    
    result = runtime.clients_repo.approve_promotion(
        request_id=payload.request_id,
        reviewer_client_id=reviewer_client_id,
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Promotion request not found or already reviewed")
    
    return ClientSummaryResponse(**result)


@router.post('/promotion/reject', response_model=dict)
async def reject_promotion(
    payload: ClientPromotionRejectRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    """Reject a promotion request (admin only)."""
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    runtime = get_runtime(request)
    reviewer_client_id = auth["client_id"]
    
    result = runtime.clients_repo.reject_promotion(
        request_id=payload.request_id,
        reviewer_client_id=reviewer_client_id,
        reason=payload.reason,
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Promotion request not found or already reviewed")
    
    return {"status": "rejected", "request_id": payload.request_id}


@router.get('/admin/list', response_model=list[ClientSummaryResponse])
async def list_admin_clients(
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    """List all admin clients (admin only)."""
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return get_runtime(request).clients_repo.get_admin_clients()


@router.patch('/{client_id}/access-tier', response_model=ClientSummaryResponse)
async def update_client_access_tier(
    client_id: str,
    payload: ClientAccessTierUpdateRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        updated = get_runtime(request).clients_repo.update_access_tier(client_id, payload.access_tier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Client not found")
    return updated


@router.post('/{client_id}/revoke', response_model=ClientSummaryResponse)
async def revoke_client(
    client_id: str,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    updated = get_runtime(request).clients_repo.revoke_client(client_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Client not found")
    return updated
