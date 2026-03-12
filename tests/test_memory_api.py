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


def issue_access_token(client_data: dict) -> str:
    response = request(
        'POST',
        '/v1/auth/token',
        json={
            'client_id': client_data['client_id'],
            'client_token': client_data['client_token'],
        },
    )
    assert response.status_code == 200
    return response.json()['access_token']


def bearer_headers(access_token: str) -> dict:
    return {'Authorization': f'Bearer {access_token}'}


def test_memory_record_create_and_list_for_authenticated_client():
    created = create_client('Memory Client')
    token = issue_access_token(created)

    create_response = request(
        'POST',
        '/v1/memory/records',
        json={
            'memory_type': 'fact',
            'content': 'User prefers concise answers.',
            'summary': 'Preference: concise responses',
            'tags': ['preference', 'style'],
            'importance': 0.9,
            'source': 'alfred',
        },
        headers=bearer_headers(token),
    )
    assert create_response.status_code == 200
    created_record = create_response.json()
    assert created_record['client_id'] == created['client_id']
    assert created_record['memory_type'] == 'fact'

    list_response = request('GET', '/v1/memory/records', headers=bearer_headers(token))
    assert list_response.status_code == 200
    records = list_response.json()
    assert any(record['record_id'] == created_record['record_id'] for record in records)


def test_memory_record_list_filters():
    created = create_client('Memory Filter Client')
    token = issue_access_token(created)
    headers = bearer_headers(token)

    request(
        'POST',
        '/v1/memory/records',
        json={
            'memory_type': 'task',
            'content': 'Follow up on deployment health checks',
            'tags': ['ops'],
            'importance': 0.6,
            'source': 'alfred',
        },
        headers=headers,
    )
    request(
        'POST',
        '/v1/memory/records',
        json={
            'memory_type': 'fact',
            'content': 'Preferred timezone is America/Denver',
            'tags': ['profile'],
            'importance': 0.8,
            'source': 'import',
        },
        headers=headers,
    )

    filtered = request('GET', '/v1/memory/records?memory_type=fact&tag=profile&source=import', headers=headers)
    assert filtered.status_code == 200
    rows = filtered.json()
    assert len(rows) >= 1
    assert all(row['memory_type'] == 'fact' for row in rows)
    assert all('profile' in row['tags'] for row in rows)
    assert all(row['source'] == 'import' for row in rows)


def test_memory_record_cross_client_access_is_forbidden():
    client_a = create_client('Memory A')
    client_b = create_client('Memory B')
    token_a = issue_access_token(client_a)
    token_b = issue_access_token(client_b)

    create_response = request(
        'POST',
        '/v1/memory/records',
        json={
            'memory_type': 'fact',
            'content': 'Only client A should see this.',
        },
        headers=bearer_headers(token_a),
    )
    assert create_response.status_code == 200

    forbidden = request(
        'GET',
        f"/v1/memory/records?client_id={client_a['client_id']}",
        headers=bearer_headers(token_b),
    )
    assert forbidden.status_code == 403


def test_admin_can_write_and_read_memory_for_any_client():
    target = create_client('Admin Target Client')

    created = request(
        'POST',
        '/v1/memory/records',
        json={
            'client_id': target['client_id'],
            'memory_type': 'fact',
            'content': 'Admin inserted memory record',
            'tags': ['admin'],
        },
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert created.status_code == 200
    assert created.json()['client_id'] == target['client_id']

    listed = request(
        'GET',
        f"/v1/memory/records?client_id={target['client_id']}",
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert listed.status_code == 200
    assert any(row['content'] == 'Admin inserted memory record' for row in listed.json())


def test_memory_record_get_patch_delete_lifecycle():
    created = create_client('Lifecycle Client')
    token = issue_access_token(created)
    headers = bearer_headers(token)

    created_record = request(
        'POST',
        '/v1/memory/records',
        json={
            'memory_type': 'fact',
            'content': 'Original content',
            'summary': 'Original summary',
            'tags': ['one'],
            'importance': 0.4,
            'source': 'alfred',
        },
        headers=headers,
    ).json()
    record_id = created_record['record_id']

    fetched = request('GET', f'/v1/memory/records/{record_id}', headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()['content'] == 'Original content'

    patched = request(
        'PATCH',
        f'/v1/memory/records/{record_id}',
        json={
            'content': 'Updated content',
            'summary': None,
            'tags': ['one', 'two'],
            'importance': 0.95,
        },
        headers=headers,
    )
    assert patched.status_code == 200
    patched_body = patched.json()
    assert patched_body['content'] == 'Updated content'
    assert patched_body['summary'] is None
    assert patched_body['tags'] == ['one', 'two']
    assert patched_body['importance'] == 0.95

    deleted = request('DELETE', f'/v1/memory/records/{record_id}', headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {'deleted': True}

    missing_after_delete = request('GET', f'/v1/memory/records/{record_id}', headers=headers)
    assert missing_after_delete.status_code == 404


def test_memory_record_record_level_authorization():
    client_a = create_client('Record Auth A')
    client_b = create_client('Record Auth B')
    token_a = issue_access_token(client_a)
    token_b = issue_access_token(client_b)

    created = request(
        'POST',
        '/v1/memory/records',
        json={'memory_type': 'fact', 'content': 'A-only record'},
        headers=bearer_headers(token_a),
    )
    assert created.status_code == 200
    record_id = created.json()['record_id']

    forbidden_get = request('GET', f'/v1/memory/records/{record_id}', headers=bearer_headers(token_b))
    assert forbidden_get.status_code == 403

    forbidden_patch = request(
        'PATCH',
        f'/v1/memory/records/{record_id}',
        json={'content': 'B should not update'},
        headers=bearer_headers(token_b),
    )
    assert forbidden_patch.status_code == 403

    forbidden_delete = request('DELETE', f'/v1/memory/records/{record_id}', headers=bearer_headers(token_b))
    assert forbidden_delete.status_code == 403


def test_admin_can_manage_record_level_memory_for_other_client():
    target = create_client('Record Admin Target')
    created = request(
        'POST',
        '/v1/memory/records',
        json={
            'client_id': target['client_id'],
            'memory_type': 'fact',
            'content': 'Admin-owned for target',
        },
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert created.status_code == 200
    record_id = created.json()['record_id']

    fetched = request(
        'GET',
        f'/v1/memory/records/{record_id}',
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert fetched.status_code == 200

    patched = request(
        'PATCH',
        f'/v1/memory/records/{record_id}',
        json={'summary': 'updated by admin'},
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert patched.status_code == 200
    assert patched.json()['summary'] == 'updated by admin'

    deleted = request(
        'DELETE',
        f'/v1/memory/records/{record_id}',
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert deleted.status_code == 200


def test_memory_summary_create_list_latest_and_get():
    created = create_client('Summary Client')
    token = issue_access_token(created)
    headers = bearer_headers(token)

    first = request(
        'POST',
        '/v1/memory/summaries',
        json={
            'conversation_id': 'conv-1',
            'context_version': 'v1',
            'summary': 'First summary',
            'source': 'alfred',
        },
        headers=headers,
    )
    assert first.status_code == 200
    first_body = first.json()

    second = request(
        'POST',
        '/v1/memory/summaries',
        json={
            'conversation_id': 'conv-1',
            'context_version': 'v2',
            'summary': 'Second summary',
            'source': 'orty',
        },
        headers=headers,
    )
    assert second.status_code == 200
    second_body = second.json()

    listed = request('GET', '/v1/memory/summaries?conversation_id=conv-1', headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) >= 2

    latest = request('GET', '/v1/memory/summaries/latest?conversation_id=conv-1', headers=headers)
    assert latest.status_code == 200
    assert latest.json()['summary_id'] == second_body['summary_id']

    fetched = request('GET', f"/v1/memory/summaries/{first_body['summary_id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()['summary'] == 'First summary'


def test_memory_summary_cross_client_forbidden():
    client_a = create_client('Summary A')
    client_b = create_client('Summary B')
    token_a = issue_access_token(client_a)
    token_b = issue_access_token(client_b)

    created = request(
        'POST',
        '/v1/memory/summaries',
        json={
            'conversation_id': 'conv-shared',
            'summary': 'Client A summary',
        },
        headers=bearer_headers(token_a),
    )
    assert created.status_code == 200
    summary_id = created.json()['summary_id']

    forbidden_get = request('GET', f'/v1/memory/summaries/{summary_id}', headers=bearer_headers(token_b))
    assert forbidden_get.status_code == 403

    forbidden_list = request(
        'GET',
        f"/v1/memory/summaries?client_id={client_a['client_id']}",
        headers=bearer_headers(token_b),
    )
    assert forbidden_list.status_code == 403
