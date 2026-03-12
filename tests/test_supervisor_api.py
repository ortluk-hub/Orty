import asyncio
import tempfile

import pytest

from service.config import settings
from service.security import verify_client_token
from service.supervisor.bot_types import code_review


async def request(client, method: str, path: str, **kwargs):
    return await client.request(method, path, **kwargs)


async def create_client(client, name: str) -> dict:
    response = await request(
        client,
        'POST',
        '/v1/clients',
        json={'name': name},
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert response.status_code == 200
    return response.json()


def client_headers(client_data: dict) -> dict:
    return {
        'x-orty-client-id': client_data['client_id'],
        'x-orty-client-token': client_data['client_token'],
    }


@pytest.mark.anyio
async def test_client_creation_requires_admin_secret(async_client):
    unauthorized = await request(async_client, 'POST', '/v1/clients', json={'name': 'No Secret'})
    assert unauthorized.status_code == 422


@pytest.mark.anyio
async def test_client_creation_and_token_verification(async_client):
    created = await create_client(async_client, 'Kitchen Tablet')

    assert created['client_id']
    assert created['client_token']
    assert verify_client_token(created['client_id'], created['client_token'])
    assert not verify_client_token(created['client_id'], 'bad-token')


@pytest.mark.anyio
async def test_bot_lifecycle_start_heartbeat_stop_and_events(async_client):
    created_client = await create_client(async_client, 'Bot Owner')
    headers = client_headers(created_client)

    create_response = await request(
        async_client,
        'POST',
        '/v1/bots',
        json={'bot_type': 'heartbeat', 'config': {'interval_seconds': 1}},
        headers=headers,
    )
    assert create_response.status_code == 200
    bot_id = create_response.json()['bot_id']

    start_response = await request(async_client, 'POST', f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 200
    assert start_response.json()['status'] == 'running'

    await asyncio.sleep(1.2)

    events_response = await request(async_client, 'GET', f'/v1/bots/{bot_id}/events?limit=20', headers=headers)
    assert events_response.status_code == 200
    event_types = [event['event_type'] for event in events_response.json()]
    assert 'STARTED' in event_types
    assert 'HEARTBEAT' in event_types

    stop_response = await request(async_client, 'POST', f'/v1/bots/{bot_id}/stop', headers=headers)
    assert stop_response.status_code == 200
    assert stop_response.json()['status'] == 'stopped'

    events_after_stop = await request(async_client, 'GET', f'/v1/bots/{bot_id}/events?limit=20', headers=headers)
    assert events_after_stop.status_code == 200
    after_stop_types = [event['event_type'] for event in events_after_stop.json()]
    assert 'STOPPED' in after_stop_types


@pytest.mark.anyio
async def test_client_auth_scoping_blocks_cross_client_access(async_client):
    client_a = await create_client(async_client, 'Client A')
    client_b = await create_client(async_client, 'Client B')

    bot_created = await request(
        async_client,
        'POST',
        '/v1/bots',
        json={'bot_type': 'heartbeat', 'config': {'interval_seconds': 1}},
        headers=client_headers(client_a),
    )
    assert bot_created.status_code == 200
    bot_id = bot_created.json()['bot_id']

    forbidden = await request(async_client, 'GET', f'/v1/bots/{bot_id}', headers=client_headers(client_b))
    assert forbidden.status_code == 403


@pytest.mark.anyio
async def test_clients_list_requires_admin_secret(async_client):
    unauthorized = await request(async_client, 'GET', '/v1/clients')
    assert unauthorized.status_code == 422

    authorized = await request(async_client, 'GET', '/v1/clients', headers={'x-orty-secret': settings.ORTY_SHARED_SECRET})
    assert authorized.status_code == 200
    assert isinstance(authorized.json(), list)


@pytest.mark.anyio
async def test_start_rejects_unsupported_bot_type_without_transitioning_to_running(async_client):
    created_client = await create_client(async_client, 'Unsupported Type Owner')
    headers = client_headers(created_client)

    create_response = await request(
        async_client,
        'POST',
        '/v1/bots',
        json={'bot_type': 'not_real', 'config': {}},
        headers=headers,
    )
    assert create_response.status_code == 200
    bot_id = create_response.json()['bot_id']

    start_response = await request(async_client, 'POST', f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 409
    assert "Unsupported bot type" in start_response.json()['detail']

    bot_response = await request(async_client, 'GET', f'/v1/bots/{bot_id}', headers=headers)
    assert bot_response.status_code == 200
    assert bot_response.json()['status'] == 'created'


@pytest.mark.anyio
async def test_start_rejects_non_positive_heartbeat_interval(async_client):
    created_client = await create_client(async_client, 'Zero Interval Owner')
    headers = client_headers(created_client)

    create_response = await request(
        async_client,
        'POST',
        '/v1/bots',
        json={'bot_type': 'heartbeat', 'config': {'interval_seconds': 0}},
        headers=headers,
    )
    assert create_response.status_code == 200
    bot_id = create_response.json()['bot_id']

    start_response = await request(async_client, 'POST', f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 422
    assert 'interval_seconds must be greater than 0' == start_response.json()['detail']

    bot_response = await request(async_client, 'GET', f'/v1/bots/{bot_id}', headers=headers)
    assert bot_response.status_code == 200
    assert bot_response.json()['status'] == 'created'


@pytest.mark.anyio
async def test_code_review_bot_clones_repo_and_emits_human_review_proposals(async_client, monkeypatch):
    monkeypatch.setattr(code_review, "_clone_repo", lambda repository_url, branch: tempfile.mkdtemp(prefix="orty-review-test-"))
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    seeded_chat = await request(
        async_client,
        'POST',
        '/chat',
        json={'message': 'We should improve safer tool contracts and add automation hooks.'},
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert seeded_chat.status_code == 200
    conversation_id = seeded_chat.json()['conversation_id']

    created_client = await create_client(async_client, 'Code Review Owner')
    headers = client_headers(created_client)

    create_response = await request(
        async_client,
        'POST',
        '/v1/bots',
        json={
            'bot_type': 'code_review',
            'config': {
                'repository_url': '.',
                'conversation_id': conversation_id,
                'roadmap_text': 'Safer, extensible tool contracts\nAutomation + integration expansion',
                'max_proposals': 2,
            },
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    bot_id = create_response.json()['bot_id']

    start_response = await request(async_client, 'POST', f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 200

    events = []
    for _ in range(40):
        await asyncio.sleep(0.25)
        events_response = await request(async_client, 'GET', f'/v1/bots/{bot_id}/events?limit=20', headers=headers)
        assert events_response.status_code == 200
        events = events_response.json()
        event_types = [event['event_type'] for event in events]
        if 'REPO_CLONED' in event_types and 'REVIEW_COMPLETED' in event_types:
            break
    event_types = [event['event_type'] for event in events]

    assert 'REVIEW_STARTED' in event_types


@pytest.mark.anyio
async def test_automation_extensions_bot_emits_planning_events(async_client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    seeded_chat = await request(
        async_client,
        'POST',
        '/chat',
        json={'message': 'Please add github automation first.'},
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert seeded_chat.status_code == 200
    conversation_id = seeded_chat.json()['conversation_id']

    created_client = await create_client(async_client, 'Automation Extensions Owner')
    headers = client_headers(created_client)

    create_response = await request(
        async_client,
        'POST',
        '/v1/bots',
        json={
            'bot_type': 'automation_extensions',
            'config': {
                'conversation_id': conversation_id,
                'integration_targets': ['github', 'notion'],
            },
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    bot_id = create_response.json()['bot_id']

    start_response = await request(async_client, 'POST', f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 200

    for _ in range(20):
        events_response = await request(async_client, 'GET', f'/v1/bots/{bot_id}/events?limit=20', headers=headers)
        assert events_response.status_code == 200
        event_types = [event['event_type'] for event in events_response.json()]
        if 'AUTOMATION_EXTENSIONS_COMPLETED' in event_types:
            break
        await asyncio.sleep(0.1)

    assert 'AUTOMATION_EXTENSIONS_STARTED' in event_types
    assert 'AUTOMATION_EXTENSION_PLAN' in event_types
    assert 'AUTOMATION_EXTENSIONS_COMPLETED' in event_types


@pytest.mark.anyio
async def test_client_preferences_and_scoped_chat_memory(async_client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    client_a = await create_client(async_client, 'Scoped A')
    client_b = await create_client(async_client, 'Scoped B')

    update_a = await request(
        async_client,
        'PATCH',
        '/v1/clients/me/preferences',
        json={'preferences': {'theme': 'dark'}},
        headers=client_headers(client_a),
    )
    assert update_a.status_code == 200
    assert update_a.json()['preferences'] == {'theme': 'dark'}

    shared_conversation_id = 'shared-conversation'

    chat_a = await request(async_client, 'POST', '/chat', json={'message': 'alpha', 'conversation_id': shared_conversation_id}, headers=client_headers(client_a))
    assert chat_a.status_code == 200

    chat_b = await request(async_client, 'POST', '/chat', json={'message': 'beta', 'conversation_id': shared_conversation_id}, headers=client_headers(client_b))
    assert chat_b.status_code == 200

    history_a = await request(async_client, 'POST', '/chat', json={'message': 'next-a', 'conversation_id': shared_conversation_id}, headers=client_headers(client_a))
    history_b = await request(async_client, 'POST', '/chat', json={'message': 'next-b', 'conversation_id': shared_conversation_id}, headers=client_headers(client_b))

    assert history_a.status_code == 200
    assert history_b.status_code == 200
    assert history_a.json()['used_history'] == 2
    assert history_b.json()['used_history'] == 2
