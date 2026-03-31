import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from service.api import app
from service.config import settings


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def request(method: str, path: str, **kwargs) -> httpx.Response:
    return asyncio.run(_request(method, path, **kwargs))


def create_client(name: str) -> dict:
    response = request(
        'POST',
        '/v1/clients',
        json={'name': name},
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert response.status_code == 200
    return response.json()


def issue_access_token(client_data: dict) -> dict:
    response = request(
        'POST',
        '/v1/auth/token',
        json={
            'client_id': client_data['client_id'],
            'client_token': client_data['client_token'],
        },
    )
    assert response.status_code == 200
    return response.json()


def set_client_last_seen(client_id: str, when_iso: str) -> None:
    with app.state.runtime.db.connect() as conn:
        conn.execute(
            "UPDATE clients SET last_seen_at = ? WHERE client_id = ?",
            (when_iso, client_id),
        )


def test_issue_access_token_with_valid_client_credentials():
    created = create_client('Token Client')

    response = request(
        'POST',
        '/v1/auth/token',
        json={
            'client_id': created['client_id'],
            'client_token': created['client_token'],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body['access_token']
    assert body['token_type'] == 'bearer'
    assert body['client_id'] == created['client_id']
    assert body['expires_in'] > 0
    assert created['access_tier'] == 'free'
    assert created['lifecycle_status'] == 'active'


def test_issue_access_token_rejects_invalid_client_token():
    created = create_client('Bad Token Client')

    response = request(
        'POST',
        '/v1/auth/token',
        json={
            'client_id': created['client_id'],
            'client_token': 'not-valid',
        },
    )

    assert response.status_code == 401


def test_chat_accepts_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'openai')
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', None)

    created = create_client('Bearer Chat Client')
    token = issue_access_token(created)

    response = request(
        'POST',
        '/chat',
        json={'message': 'hello'},
        headers={'Authorization': f"Bearer {token['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()['conversation_id']


def test_legacy_client_headers_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, 'ALLOW_LEGACY_CLIENT_HEADERS', False)
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'openai')
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', None)

    created = create_client('Legacy Off Client')

    legacy = request(
        'POST',
        '/chat',
        json={'message': 'legacy'},
        headers={
            'x-orty-client-id': created['client_id'],
            'x-orty-client-token': created['client_token'],
        },
    )
    assert legacy.status_code == 401

    token = issue_access_token(created)
    bearer = request(
        'POST',
        '/chat',
        json={'message': 'bearer'},
        headers={'Authorization': f"Bearer {token['access_token']}"},
    )
    assert bearer.status_code == 200


def test_revoke_access_token_blocks_future_requests(monkeypatch):
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'openai')
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', None)

    created = create_client('Revoke Client')
    token = issue_access_token(created)
    bearer_headers = {'Authorization': f"Bearer {token['access_token']}"}

    before_revoke = request('POST', '/chat', json={'message': 'before revoke'}, headers=bearer_headers)
    assert before_revoke.status_code == 200

    revoke = request('POST', '/v1/auth/revoke', json={}, headers=bearer_headers)
    assert revoke.status_code == 200
    assert revoke.json() == {'revoked': True}

    after_revoke = request('POST', '/chat', json={'message': 'after revoke'}, headers=bearer_headers)
    assert after_revoke.status_code == 401


def test_rotate_client_token_invalidates_old_client_token_and_access_tokens():
    created = create_client('Rotate Client')
    token = issue_access_token(created)

    rotate = request(
        'POST',
        '/v1/auth/rotate',
        json={
            'client_id': created['client_id'],
            'client_token': created['client_token'],
            'revoke_access_tokens': True,
        },
    )
    assert rotate.status_code == 200
    rotated = rotate.json()
    assert rotated['client_id'] == created['client_id']
    assert rotated['client_token']
    assert rotated['client_token'] != created['client_token']

    old_issue = request(
        'POST',
        '/v1/auth/token',
        json={
            'client_id': created['client_id'],
            'client_token': created['client_token'],
        },
    )
    assert old_issue.status_code == 401

    new_issue = request(
        'POST',
        '/v1/auth/token',
        json={
            'client_id': created['client_id'],
            'client_token': rotated['client_token'],
        },
    )
    assert new_issue.status_code == 200

    old_bearer = request(
        'POST',
        '/chat',
        json={'message': 'old token should fail'},
        headers={'Authorization': f"Bearer {token['access_token']}"},
    )
    assert old_bearer.status_code == 401


def test_auth_me_returns_authenticated_client_context():
    created = create_client('Me Endpoint Client')
    token = issue_access_token(created)

    response = request(
        'GET',
        '/v1/auth/me',
        headers={'Authorization': f"Bearer {token['access_token']}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['client_id'] == created['client_id']
    assert body['auth_method'] == 'bearer'
    assert body['is_admin'] is False
    assert body['access_tier'] == 'free'
    assert body['lifecycle_status'] == 'active'


def test_admin_can_update_client_access_tier():
    created = create_client('Tiered Client')
    admin_headers = {'x-orty-secret': settings.ORTY_SHARED_SECRET}

    response = request(
        'PATCH',
        f"/v1/clients/{created['client_id']}/access-tier",
        json={'access_tier': 'premium'},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body['client_id'] == created['client_id']
    assert body['access_tier'] == 'premium'
    assert body['lifecycle_status'] == 'active'


def test_revoked_client_can_no_longer_authenticate_or_chat(monkeypatch):
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'openai')
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', None)

    created = create_client('Revoked Client')
    token = issue_access_token(created)

    revoke = request(
        'POST',
        f"/v1/clients/{created['client_id']}/revoke",
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert revoke.status_code == 200
    assert revoke.json()['lifecycle_status'] == 'revoked'

    token_response = request(
        'POST',
        '/v1/auth/token',
        json={
            'client_id': created['client_id'],
            'client_token': created['client_token'],
        },
    )
    assert token_response.status_code == 401

    chat = request(
        'POST',
        '/chat',
        json={'message': 'still there?'},
        headers={'Authorization': f"Bearer {token['access_token']}"},
    )
    assert chat.status_code == 401


def test_client_disconnect_revokes_itself():
    created = create_client('Disconnect Client')
    token = issue_access_token(created)
    bearer_headers = {'Authorization': f"Bearer {token['access_token']}"}

    response = request('POST', '/v1/clients/me/disconnect', headers=bearer_headers)

    assert response.status_code == 200
    body = response.json()
    assert body['client_id'] == created['client_id']
    assert body['lifecycle_status'] == 'revoked'


def test_list_clients_marks_old_clients_as_stale():
    created = create_client('Stale Client')
    stale_at = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    set_client_last_seen(created['client_id'], stale_at)

    response = request(
        'GET',
        '/v1/clients',
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )

    assert response.status_code == 200
    stale_client = next(item for item in response.json() if item['client_id'] == created['client_id'])
    assert stale_client['lifecycle_status'] == 'stale'


def test_auth_introspect_is_admin_only():
    created = create_client('Introspect Owner')
    token = issue_access_token(created)

    forbidden = request(
        'POST',
        '/v1/auth/introspect',
        json={'access_token': token['access_token']},
        headers={'Authorization': f"Bearer {token['access_token']}"},
    )
    assert forbidden.status_code == 403

    allowed = request(
        'POST',
        '/v1/auth/introspect',
        json={'access_token': token['access_token']},
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert allowed.status_code == 200
    body = allowed.json()
    assert body['found'] is True
    assert body['active'] is True
    assert body['client_id'] == created['client_id']
