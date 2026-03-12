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
        "POST",
        "/v1/clients",
        json={"name": name},
        headers={"x-orty-secret": settings.ORTY_SHARED_SECRET},
    )
    assert response.status_code == 200
    return response.json()


def issue_access_token(client_data: dict) -> str:
    response = request(
        "POST",
        "/v1/auth/token",
        json={
            "client_id": client_data["client_id"],
            "client_token": client_data["client_token"],
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def bearer_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def test_memory_sync_creates_and_returns_canonical_snapshot_for_authenticated_client():
    created = create_client("Memory Sync Client")
    token = issue_access_token(created)

    response = request(
        "POST",
        "/memory/sync",
        json={
            "client": "alfred-android",
            "memories": [
                {
                    "key": "project:alfred",
                    "category": "PROJECT",
                    "summary": "User is working on Alfred",
                    "sourceText": "I'm working on Alfred",
                    "createdAt": 1000,
                    "updatedAt": 2000,
                    "isPinned": True,
                    "expiresAt": None,
                }
            ],
        },
        headers=bearer_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["syncedCount"] == 1
    assert body["memories"][0]["key"] == "project:alfred"
    assert body["memories"][0]["isPinned"] is True

    listed = request("GET", "/v1/memory/records", headers=bearer_headers(token))
    assert listed.status_code == 200
    rows = listed.json()
    assert any(row["external_key"] == "project:alfred" for row in rows)


def test_memory_sync_is_scoped_per_authenticated_client():
    client_a = create_client("Sync A")
    client_b = create_client("Sync B")
    token_a = issue_access_token(client_a)
    token_b = issue_access_token(client_b)

    response_a = request(
        "POST",
        "/memory/sync",
        json={
            "client": "alfred-android",
            "memories": [
                {
                    "key": "project:a",
                    "category": "PROJECT",
                    "summary": "Client A memory",
                    "sourceText": "Client A memory",
                    "createdAt": 1,
                    "updatedAt": 2,
                    "isPinned": False,
                    "expiresAt": None,
                }
            ],
        },
        headers=bearer_headers(token_a),
    )
    assert response_a.status_code == 200

    response_b = request(
        "POST",
        "/memory/sync",
        json={
            "client": "alfred-android",
            "memories": [
                {
                    "key": "project:b",
                    "category": "PROJECT",
                    "summary": "Client B memory",
                    "sourceText": "Client B memory",
                    "createdAt": 1,
                    "updatedAt": 2,
                    "isPinned": False,
                    "expiresAt": None,
                }
            ],
        },
        headers=bearer_headers(token_b),
    )
    assert response_b.status_code == 200

    listed_a = request("GET", "/v1/memory/records", headers=bearer_headers(token_a))
    listed_b = request("GET", "/v1/memory/records", headers=bearer_headers(token_b))
    rows_a = listed_a.json()
    rows_b = listed_b.json()

    assert any(row["external_key"] == "project:a" for row in rows_a)
    assert all(row["external_key"] != "project:b" for row in rows_a if row["external_key"])
    assert any(row["external_key"] == "project:b" for row in rows_b)
    assert all(row["external_key"] != "project:a" for row in rows_b if row["external_key"])


def test_memory_sync_replaces_only_sync_managed_subset():
    created = create_client("Sync Replace Client")
    token = issue_access_token(created)
    headers = bearer_headers(token)

    manual = request(
        "POST",
        "/v1/memory/records",
        json={
            "memory_type": "fact",
            "content": "Manual memory record",
            "summary": "Manual memory record",
            "source": "manual",
        },
        headers=headers,
    )
    assert manual.status_code == 200

    first_sync = request(
        "POST",
        "/memory/sync",
        json={
            "client": "alfred-android",
            "memories": [
                {
                    "key": "project:one",
                    "category": "PROJECT",
                    "summary": "Sync memory one",
                    "sourceText": "Sync memory one",
                    "createdAt": 1,
                    "updatedAt": 2,
                    "isPinned": False,
                    "expiresAt": None,
                }
            ],
        },
        headers=headers,
    )
    assert first_sync.status_code == 200

    second_sync = request(
        "POST",
        "/memory/sync",
        json={
            "client": "alfred-android",
            "memories": [],
        },
        headers=headers,
    )
    assert second_sync.status_code == 200
    assert second_sync.json()["syncedCount"] == 0

    listed = request("GET", "/v1/memory/records", headers=headers)
    rows = listed.json()
    assert any(row["source"] == "manual" for row in rows)
    assert all(row["external_key"] != "project:one" for row in rows if row["external_key"])
