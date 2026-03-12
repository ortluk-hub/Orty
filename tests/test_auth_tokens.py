import asyncio

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
