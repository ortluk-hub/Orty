from fastapi import APIRouter, Depends, Header, HTTPException, Request

from service.api.deps import get_request_auth, get_runtime
from service.models.schemas import (
    ClientIntrospectRequest,
    ClientIntrospectResponse,
    ClientMeResponse,
    ClientRevokeRequest,
    ClientRevokeResponse,
    ClientRotateRequest,
    ClientRotateResponse,
    ClientTokenRequest,
    ClientTokenResponse,
)

router = APIRouter(prefix='/v1/auth', tags=['v1-auth'])


@router.post('/token', response_model=ClientTokenResponse)
async def issue_client_token(payload: ClientTokenRequest, request: Request):
    token = get_runtime(request).clients_repo.issue_access_token(payload.client_id, payload.client_token)
    if token is None:
        raise HTTPException(status_code=401, detail='Unauthorized')
    return ClientTokenResponse(**token)


@router.get('/me', response_model=ClientMeResponse)
async def auth_me(auth: dict = Depends(get_request_auth)):
    client = auth.get("client")
    if not client:
        raise HTTPException(status_code=404, detail='Client not found')
    return ClientMeResponse(
        client_id=client["client_id"],
        name=client.get("name"),
        preferences=client.get("preferences", {}),
        is_primary=bool(client.get("is_primary", False)),
        created_at=client["created_at"],
        last_seen_at=client.get("last_seen_at"),
        auth_method=str(auth.get("auth_method", "unknown")),
        is_admin=bool(auth.get("is_admin", False)),
    )


@router.post('/rotate', response_model=ClientRotateResponse)
async def rotate_client_token(payload: ClientRotateRequest, request: Request):
    rotated = get_runtime(request).clients_repo.rotate_client_token(
        payload.client_id,
        payload.client_token,
        revoke_access_tokens=payload.revoke_access_tokens,
    )
    if rotated is None:
        raise HTTPException(status_code=401, detail='Unauthorized')
    return ClientRotateResponse(**rotated)


@router.post('/revoke', response_model=ClientRevokeResponse)
async def revoke_access_token(
    payload: ClientRevokeRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
    authorization: str | None = Header(default=None),
):
    token_to_revoke = payload.access_token
    current_bearer: str | None = None
    if authorization and authorization.lower().startswith('bearer '):
        current_bearer = authorization[7:].strip()

    if token_to_revoke is None:
        token_to_revoke = current_bearer

    if not token_to_revoke:
        raise HTTPException(status_code=400, detail='No access token provided')

    is_admin = bool(auth.get("is_admin"))
    if not is_admin and token_to_revoke != current_bearer:
        raise HTTPException(status_code=403, detail='Forbidden')

    revoked = get_runtime(request).clients_repo.revoke_access_token(token_to_revoke)
    if not revoked:
        raise HTTPException(status_code=404, detail='Access token not found')
    return ClientRevokeResponse(revoked=True)


@router.post('/introspect', response_model=ClientIntrospectResponse)
async def introspect_access_token(
    payload: ClientIntrospectRequest,
    request: Request,
    auth: dict = Depends(get_request_auth),
):
    if not auth.get("is_admin"):
        raise HTTPException(status_code=403, detail='Forbidden')

    result = get_runtime(request).clients_repo.inspect_access_token(payload.access_token)
    if result is None:
        return ClientIntrospectResponse(found=False, active=False)
    return ClientIntrospectResponse(**result)
