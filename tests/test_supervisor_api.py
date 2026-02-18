import time

from fastapi.testclient import TestClient

from service.api import app
from service.config import settings
from service.security import verify_client_token


client = TestClient(app)


def create_client(name: str) -> dict:
    response = client.post('/v1/clients', json={'name': name})
    assert response.status_code == 200
    return response.json()


def client_headers(client_data: dict) -> dict:
    return {
        'x-orty-client-id': client_data['client_id'],
        'x-orty-client-token': client_data['client_token'],
    }


def test_client_creation_and_token_verification():
    created = create_client('Kitchen Tablet')

    assert created['client_id']
    assert created['client_token']
    assert verify_client_token(created['client_id'], created['client_token'])
    assert not verify_client_token(created['client_id'], 'bad-token')


def test_bot_lifecycle_start_heartbeat_stop_and_events():
    created_client = create_client('Bot Owner')
    headers = client_headers(created_client)

    create_response = client.post(
        '/v1/bots',
        json={'bot_type': 'heartbeat', 'config': {'interval_seconds': 1}},
        headers=headers,
    )
    assert create_response.status_code == 200
    bot_id = create_response.json()['bot_id']

    start_response = client.post(f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 200
    assert start_response.json()['status'] == 'running'

    time.sleep(1.2)

    events_response = client.get(f'/v1/bots/{bot_id}/events?limit=20', headers=headers)
    assert events_response.status_code == 200
    event_types = [event['event_type'] for event in events_response.json()]
    assert 'STARTED' in event_types
    assert 'HEARTBEAT' in event_types

    stop_response = client.post(f'/v1/bots/{bot_id}/stop', headers=headers)
    assert stop_response.status_code == 200
    assert stop_response.json()['status'] == 'stopped'

    events_after_stop = client.get(f'/v1/bots/{bot_id}/events?limit=20', headers=headers)
    assert events_after_stop.status_code == 200
    after_stop_types = [event['event_type'] for event in events_after_stop.json()]
    assert 'STOPPED' in after_stop_types


def test_client_auth_scoping_blocks_cross_client_access():
    client_a = create_client('Client A')
    client_b = create_client('Client B')

    bot_created = client.post(
        '/v1/bots',
        json={'bot_type': 'heartbeat', 'config': {'interval_seconds': 1}},
        headers=client_headers(client_a),
    )
    assert bot_created.status_code == 200
    bot_id = bot_created.json()['bot_id']

    forbidden = client.get(f'/v1/bots/{bot_id}', headers=client_headers(client_b))
    assert forbidden.status_code == 403


def test_clients_list_requires_admin_secret():
    unauthorized = client.get('/v1/clients')
    assert unauthorized.status_code == 422

    authorized = client.get('/v1/clients', headers={'x-orty-secret': settings.ORTY_SHARED_SECRET})
    assert authorized.status_code == 200
    assert isinstance(authorized.json(), list)

def test_start_rejects_unsupported_bot_type_without_transitioning_to_running():
    created_client = create_client('Unsupported Type Owner')
    headers = client_headers(created_client)

    create_response = client.post(
        '/v1/bots',
        json={'bot_type': 'not_real', 'config': {}},
        headers=headers,
    )
    assert create_response.status_code == 200
    bot_id = create_response.json()['bot_id']

    start_response = client.post(f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 409
    assert "Unsupported bot type" in start_response.json()['detail']

    bot_response = client.get(f'/v1/bots/{bot_id}', headers=headers)
    assert bot_response.status_code == 200
    assert bot_response.json()['status'] == 'created'


def test_start_rejects_non_positive_heartbeat_interval():
    created_client = create_client('Zero Interval Owner')
    headers = client_headers(created_client)

    create_response = client.post(
        '/v1/bots',
        json={'bot_type': 'heartbeat', 'config': {'interval_seconds': 0}},
        headers=headers,
    )
    assert create_response.status_code == 200
    bot_id = create_response.json()['bot_id']

    start_response = client.post(f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 422
    assert 'interval_seconds must be greater than 0' == start_response.json()['detail']

    bot_response = client.get(f'/v1/bots/{bot_id}', headers=headers)
    assert bot_response.status_code == 200
    assert bot_response.json()['status'] == 'created'


def test_code_review_bot_clones_repo_and_emits_human_review_proposals(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    seeded_chat = client.post(
        '/chat',
        json={'message': 'We should improve safer tool contracts and add automation hooks.'},
        headers={'x-orty-secret': settings.ORTY_SHARED_SECRET},
    )
    assert seeded_chat.status_code == 200
    conversation_id = seeded_chat.json()['conversation_id']

    created_client = create_client('Code Review Owner')
    headers = client_headers(created_client)

    create_response = client.post(
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

    start_response = client.post(f'/v1/bots/{bot_id}/start', headers=headers)
    assert start_response.status_code == 200

    time.sleep(2.0)

    events_response = client.get(f'/v1/bots/{bot_id}/events?limit=20', headers=headers)
    assert events_response.status_code == 200
    events = events_response.json()
    event_types = [event['event_type'] for event in events]

    assert 'REVIEW_STARTED' in event_types
    assert 'REPO_CLONED' in event_types
    assert 'REVIEW_PROPOSAL' in event_types
    assert 'REVIEW_COMPLETED' in event_types

    proposal_event = next(event for event in events if event['event_type'] == 'REVIEW_PROPOSAL')
    assert proposal_event['payload']['human_review_required'] is True
    assert proposal_event['payload']['considered_memory_messages'] >= 1
    assert len(proposal_event['payload']['proposals']) == 2
